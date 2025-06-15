"""
Web Scraping Module for Documentation Generation

This module provides comprehensive web scraping functionality to extract HTML content
and recursively crawl websites for documentation generation using LLMs.

Features:
- Extract HTML content from URLs
- Parse and clean HTML content
- Recursive link discovery and crawling
- Rate limiting and respectful crawling
- Content filtering and deduplication
- Export functionality for LLM processing

Author: Generated for documentation creation
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser
import time
import re
import json
import hashlib
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from pathlib import Path
import csv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class PageContent:
    """Data class to store extracted page content"""
    url: str
    title: str
    content: str
    links: List[str]
    meta_description: str
    headers: List[str]
    timestamp: str
    status_code: int
    content_hash: str

class WebScraper:
    """
    Main web scraping class with recursive crawling capabilities
    """
   
    def __init__(self,
                 delay: float = 1.0,
                 max_workers: int = 5,
                 timeout: int = 30,
                 max_depth: int = 3,
                 user_agent: str = "DocumentationBot/1.0"):
        """
        Initialize the web scraper
       
        Args:
            delay: Delay between requests in seconds
            max_workers: Maximum number of concurrent workers
            timeout: Request timeout in seconds
            max_depth: Maximum crawling depth
            user_agent: User agent string for requests
        """
        self.delay = delay
        self.max_workers = max_workers
        self.timeout = timeout
        self.max_depth = max_depth
        self.user_agent = user_agent
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': user_agent})
        self.visited_urls: Set[str] = set()
        self.scraped_content: List[PageContent] = []
       
    def normalize_url(self, url: str) -> str:
        """
        Normalize URL by removing fragments and query parameters
       
        Args:
            url: Raw URL string
           
        Returns:
            Normalized URL string
        """
        parsed = urlparse(url)
        # Remove fragment and some query parameters that don't affect content
        normalized = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            '',  # Remove query for now - could be made configurable
            ''   # Remove fragment
        ))
        return normalized.rstrip('/')
   
    def is_valid_url(self, url: str, base_domain: str) -> bool:
        """
        Check if URL is valid and within the same domain
       
        Args:
            url: URL to validate
            base_domain: Base domain to restrict crawling to
           
        Returns:
            True if URL is valid and within domain
        """
        try:
            parsed = urlparse(url)
           
            # Check if it's a valid HTTP/HTTPS URL
            if parsed.scheme not in ['http', 'https']:
                return False
               
            # Check if it's within the same domain
            if parsed.netloc != base_domain:
                return False
               
            # Skip common non-content URLs
            skip_extensions = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
                             '.zip', '.rar', '.tar', '.gz', '.jpg', '.jpeg', '.png',
                             '.gif', '.svg', '.ico', '.css', '.js', '.xml', '.json'}
           
            if any(parsed.path.lower().endswith(ext) for ext in skip_extensions):
                return False
               
            # Skip URLs with certain patterns
            skip_patterns = ['/admin', '/login', '/logout', '/register', '/search',
                           '/download', '/upload', '/api/', '/ajax/']
           
            if any(pattern in parsed.path.lower() for pattern in skip_patterns):
                return False
               
            return True
           
        except Exception as e:
            logger.error(f"Error validating URL {url}: {e}")
            return False
   
    def extract_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """
        Extract all valid links from a BeautifulSoup object
       
        Args:
            soup: BeautifulSoup object of the page
            base_url: Base URL for resolving relative links
           
        Returns:
            List of absolute URLs
        """
        links = []
        base_domain = urlparse(base_url).netloc
       
        # Extract links from <a> tags
        for link in soup.find_all('a', href=True):
            href = link['href'].strip()
            if href:
                absolute_url = urljoin(base_url, href)
                normalized_url = self.normalize_url(absolute_url)
               
                if self.is_valid_url(normalized_url, base_domain):
                    links.append(normalized_url)
       
        return list(set(links))  # Remove duplicates
   
    def extract_content(self, soup: BeautifulSoup) -> Dict[str, any]:
        """
        Extract meaningful content from a BeautifulSoup object
       
        Args:
            soup: BeautifulSoup object of the page
           
        Returns:
            Dictionary containing extracted content
        """
        # Extract title
        title = ""
        if soup.title:
            title = soup.title.get_text().strip()
       
        # Extract meta description
        meta_desc = ""
        meta_tag = soup.find('meta', attrs={'name': 'description'})
        if meta_tag and meta_tag.get('content'):
            meta_desc = meta_tag['content'].strip()
       
        # Extract headers
        headers = []
        for tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            header_text = tag.get_text().strip()
            if header_text:
                headers.append(f"{tag.name.upper()}: {header_text}")
       
        # Remove unwanted elements
        for element in soup(['script', 'style', 'nav', 'footer', 'header',
                           'aside', 'iframe', 'noscript']):
            element.decompose()
       
        # Extract main content
        main_content = ""
       
        # Try to find main content areas
        content_selectors = [
            'main', 'article', '[role="main"]', '.content', '.main-content',
            '.post-content', '.entry-content', '#content', '#main'
        ]
       
        content_element = None
        for selector in content_selectors:
            content_element = soup.select_one(selector)
            if content_element:
                break
       
        # If no main content area found, use body
        if not content_element:
            content_element = soup.find('body')
       
        if content_element:
            # Extract text content
            text_content = content_element.get_text(separator=' ', strip=True)
            # Clean up whitespace
            main_content = re.sub(r'\s+', ' ', text_content).strip()
       
        return {
            'title': title,
            'content': main_content,
            'meta_description': meta_desc,
            'headers': headers
        }
   
    def fetch_page(self, url: str) -> Optional[PageContent]:
        """
        Fetch and parse a single page
       
        Args:
            url: URL to fetch
           
        Returns:
            PageContent object or None if failed
        """
        try:
            logger.info(f"Fetching: {url}")
           
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
           
            # Parse HTML
            soup = BeautifulSoup(response.content, 'html.parser')
           
            # Extract content
            content_data = self.extract_content(soup)
           
            # Extract links
            links = self.extract_links(soup, url)
           
            # Create content hash for deduplication
            content_hash = hashlib.md5(content_data['content'].encode()).hexdigest()
           
            # Create PageContent object
            page_content = PageContent(
                url=url,
                title=content_data['title'],
                content=content_data['content'],
                links=links,
                meta_description=content_data['meta_description'],
                headers=content_data['headers'],
                timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
                status_code=response.status_code,
                content_hash=content_hash
            )
           
            return page_content
           
        except requests.RequestException as e:
            logger.error(f"Request error for {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error processing {url}: {e}")
            return None
   
    def crawl_recursive(self, start_url: str, max_depth: int = None) -> List[PageContent]:
        """
        Recursively crawl website starting from a given URL
       
        Args:
            start_url: Starting URL for crawling
            max_depth: Maximum depth to crawl (overrides instance setting)
           
        Returns:
            List of PageContent objects
        """
        if max_depth is None:
            max_depth = self.max_depth
           
        urls_to_visit = [(start_url, 0)]  # (url, depth)
        self.visited_urls.clear()
        self.scraped_content.clear()
       
        while urls_to_visit:
            current_url, depth = urls_to_visit.pop(0)
           
            # Skip if already visited or max depth reached
            if current_url in self.visited_urls or depth > max_depth:
                continue
           
            self.visited_urls.add(current_url)
           
            # Fetch page content
            page_content = self.fetch_page(current_url)
           
            if page_content:
                self.scraped_content.append(page_content)
               
                # Add found links to crawl queue if within depth limit
                if depth < max_depth:
                    for link in page_content.links:
                        if link not in self.visited_urls:
                            urls_to_visit.append((link, depth + 1))
           
            # Respectful crawling - add delay
            if self.delay > 0:
                time.sleep(self.delay)
       
        logger.info(f"Crawling completed. Scraped {len(self.scraped_content)} pages.")
        return self.scraped_content
   
    def crawl_concurrent(self, urls: List[str]) -> List[PageContent]:
        """
        Crawl multiple URLs concurrently
       
        Args:
            urls: List of URLs to crawl
           
        Returns:
            List of PageContent objects
        """
        results = []
       
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all URLs for processing
            future_to_url = {executor.submit(self.fetch_page, url): url for url in urls}
           
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    page_content = future.result()
                    if page_content:
                        results.append(page_content)
                except Exception as e:
                    logger.error(f"Error processing {url}: {e}")
               
                # Add delay to respect rate limits
                if self.delay > 0:
                    time.sleep(self.delay)
       
        return results
   
    def export_to_json(self, filename: str = "scraped_content.json") -> None:
        """
        Export scraped content to JSON file
       
        Args:
            filename: Output filename
        """
        try:
            data = [asdict(content) for content in self.scraped_content]
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Content exported to {filename}")
        except Exception as e:
            logger.error(f"Error exporting to JSON: {e}")
   
    def export_to_csv(self, filename: str = "scraped_content.csv") -> None:
        """
        Export scraped content to CSV file
       
        Args:
            filename: Output filename
        """
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                if self.scraped_content:
                    writer = csv.DictWriter(f, fieldnames=asdict(self.scraped_content[0]).keys())
                    writer.writeheader()
                    for content in self.scraped_content:
                        row = asdict(content)
                        # Convert lists to strings for CSV
                        row['links'] = '; '.join(row['links'])
                        row['headers'] = '; '.join(row['headers'])
                        writer.writerow(row)
            logger.info(f"Content exported to {filename}")
        except Exception as e:
            logger.error(f"Error exporting to CSV: {e}")
   
    def export_for_llm(self, filename: str = "content_for_llm.txt") -> None:
        """
        Export content in a format optimized for LLM processing
       
        Args:
            filename: Output filename
        """
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("WEBSITE DOCUMENTATION CONTENT\n")
                f.write("=" * 50 + "\n\n")
               
                for i, content in enumerate(self.scraped_content, 1):
                    f.write(f"PAGE {i}: {content.title}\n")
                    f.write(f"URL: {content.url}\n")
                    f.write(f"META DESCRIPTION: {content.meta_description}\n")
                    f.write("-" * 30 + "\n")
                   
                    if content.headers:
                        f.write("HEADERS:\n")
                        for header in content.headers:
                            f.write(f"- {header}\n")
                        f.write("\n")
                   
                    f.write("CONTENT:\n")
                    f.write(content.content)
                    f.write("\n\n" + "=" * 50 + "\n\n")
           
            logger.info(f"LLM-optimized content exported to {filename}")
        except Exception as e:
            logger.error(f"Error exporting for LLM: {e}")
   
    def get_content_stats(self) -> Dict[str, any]:
        """
        Get statistics about scraped content
       
        Returns:
            Dictionary with content statistics
        """
        if not self.scraped_content:
            return {"total_pages": 0}
       
        total_content_length = sum(len(content.content) for content in self.scraped_content)
        unique_domains = len(set(urlparse(content.url).netloc for content in self.scraped_content))
       
        return {
            "total_pages": len(self.scraped_content),
            "total_content_length": total_content_length,
            "average_content_length": total_content_length // len(self.scraped_content),
            "unique_domains": unique_domains,
            "total_links_found": sum(len(content.links) for content in self.scraped_content)
        }

# Convenience functions
def scrape_single_page(url: str, **kwargs) -> Optional[PageContent]:
    """
    Scrape a single page
   
    Args:
        url: URL to scrape
        **kwargs: Additional arguments for WebScraper
       
    Returns:
        PageContent object or None
    """
    scraper = WebScraper(**kwargs)
    return scraper.fetch_page(url)

def scrape_website(start_url: str, max_depth: int = 2, **kwargs) -> List[PageContent]:
    """
    Scrape entire website recursively
   
    Args:
        start_url: Starting URL
        max_depth: Maximum crawling depth
        **kwargs: Additional arguments for WebScraper
       
    Returns:
        List of PageContent objects
    """
    scraper = WebScraper(max_depth=max_depth, **kwargs)
    return scraper.crawl_recursive(start_url)

def scrape_urls(urls: List[str], **kwargs) -> List[PageContent]:
    """
    Scrape multiple URLs concurrently
   
    Args:
        urls: List of URLs to scrape
        **kwargs: Additional arguments for WebScraper
       
    Returns:
        List of PageContent objects
    """
    scraper = WebScraper(**kwargs)
    return scraper.crawl_concurrent(urls)

if __name__ == "__main__":
    # Test the scraping functionality
    test_url = "https://example.com"
   
    print("Testing single page scraping...")
    page = scrape_single_page(test_url)
    if page:
        print(f"Successfully scraped: {page.title}")
        print(f"Content length: {len(page.content)}")
        print(f"Links found: {len(page.links)}")
    else:
        print("Failed to scrape the page")
   
    print("\nTesting recursive website scraping...")
    scraper = WebScraper(delay=1.0, max_depth=15)
    pages = scraper.crawl_recursive(test_url)
   
    print(f"Scraped {len(pages)} pages")
   
    if pages:
        # Export results
        scraper.export_to_json("test_output.json")
        scraper.export_for_llm("test_content_for_llm.txt")
       
        # Print statistics
        stats = scraper.get_content_stats()
        print("\nScraping Statistics:")
        for key, value in stats.items():
            print(f"- {key.replace('_', ' ').title()}: {value}")