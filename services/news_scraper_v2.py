"""
News Scraper V2 using PyGoogleNews with advanced content cleaning
Migrated from news_scraper.ipynb notebook
"""

from pygooglenews import GoogleNews
from newspaper import Article
from googlenewsdecoder import new_decoderv1
import re
import time
from typing import List, Dict, Any, Optional
from config import settings


def clean_article_text(text: str) -> str:
    """
    Comprehensive cleaning of article text to remove boilerplate, ads, and noise
    Returns clean paragraphs of article content only
    """
    if not text or len(text.strip()) == 0:
        return ""
    
    # Step 1: Remove email addresses
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '', text)
    
    # Step 2: Remove URLs
    text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
    text = re.sub(r'www\.(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
    
    # Step 3: Remove LaTeX patterns
    text = re.sub(r'\$.*?\$', '', text)  # Inline math
    text = re.sub(r'\$\$.*?\$\$', '', text, flags=re.DOTALL)  # Display math
    text = re.sub(r'\\\[.*?\\\]', '', text, flags=re.DOTALL)  # Display math
    text = re.sub(r'\\\(.*?\\\)', '', text, flags=re.DOTALL)  # Display math
    text = re.sub(r'\\begin\{[a-z]+\*?\}.*?\\end\{[a-z]+\*?\}', '', text, flags=re.DOTALL)  # Environments
    text = re.sub(r'\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^\}]*\})?', '', text)  # Commands
    
    # Step 4: Remove common boilerplate patterns
    boilerplate_patterns = [
        r'(?i)subscribe to our newsletter',
        r'(?i)sign up for our newsletter',
        r'(?i)follow us on',
        r'(?i)share this article',
        r'(?i)read more:',
        r'(?i)advertisement',
        r'(?i)click here',
        r'(?i)related articles',
        r'(?i)you may also like',
        r'(?i)recommended for you',
        r'(?i)terms of service',
        r'(?i)privacy policy',
        r'(?i)cookie policy',
        r'(?i)all rights reserved',
        r'(?i)copyright ©',
        r'©\s*\d{4}',
        r'(?i)join our community',
        r'(?i)get the latest',
        r'(?i)breaking news',
        r'(?i)trending now',
    ]
    
    for pattern in boilerplate_patterns:
        text = re.sub(pattern + r'[^.!?]*[.!?]', '', text)
    
    # Step 5: Split into sentences and filter
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    # Filter out short sentences (likely navigation/ads)
    cleaned_sentences = []
    for sentence in sentences:
        sentence = sentence.strip()
        
        # Skip if too short (less than 10 words)
        word_count = len(sentence.split())
        if word_count < 10:
            continue
        
        # Skip if contains too many capital letters (likely navigation)
        capitals = sum(1 for c in sentence if c.isupper())
        if len(sentence) > 0 and capitals / len(sentence) > 0.3:
            continue
        
        # Skip sentences with common navigation patterns
        nav_keywords = ['facebook', 'twitter', 'instagram', 'linkedin', 'youtube', 
                       'subscribe', 'newsletter', 'advertisement', 'sponsored']
        if any(keyword in sentence.lower() for keyword in nav_keywords):
            continue
        
        cleaned_sentences.append(sentence)
    
    # Step 6: Remove excessive punctuation and special characters
    cleaned_text = ' '.join(cleaned_sentences)
    cleaned_text = re.sub(r'[^\w\s.,!?;:\'\"\-()]', ' ', cleaned_text)
    
    # Step 7: Remove excessive whitespace (including newlines)
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text)
    cleaned_text = cleaned_text.strip()
    
    # Step 8: Format into paragraphs (split long text every 4 sentences)
    sentences = re.split(r'(?<=[.!?])\s+', cleaned_text)
    paragraphs = []
    current_paragraph = []
    
    for i, sentence in enumerate(sentences):
        current_paragraph.append(sentence)
        
        # Create a new paragraph every 4 sentences
        if (i + 1) % 4 == 0 and len(current_paragraph) > 0:
            paragraphs.append(' '.join(current_paragraph))
            current_paragraph = []
    
    # Add remaining sentences
    if current_paragraph:
        paragraphs.append(' '.join(current_paragraph))
    
    # Join paragraphs with double line breaks
    final_text = '\n\n'.join(paragraphs)
    
    return final_text


def decode_google_news_url(google_url: str, max_retries: int = 3) -> Optional[str]:
    """
    Decode Google News URL to get the actual article URL
    """
    for attempt in range(max_retries):
        try:
            result = new_decoderv1(google_url, interval=2)
            
            if result.get('status'):
                decoded_url = result.get('decoded_url')
                if decoded_url and 'http' in decoded_url:
                    return decoded_url
            
            if attempt < max_retries - 1:
                time.sleep(2)
        
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                print(f"Error decoding URL: {str(e)}")
    
    return None


def extract_full_article(url: str) -> Dict[str, Any]:
    """
    Extract and clean full article content
    Returns dict with article data
    """
    try:
        original_url = url
        
        # Decode Google News URL if needed
        if 'news.google.com' in url:
            url = decode_google_news_url(url)
            
            if not url:
                return {
                    'url': original_url,
                    'resolved_url': None,
                    'title': 'Error',
                    'authors': '',
                    'publish_date': None,
                    'raw_content': '',
                    'cleaned_content': '',
                    'top_image': '',
                    'keywords': '',
                    'extraction_status': 'Failed: Could not decode Google News URL'
                }
        
        # Extract article content
        article = Article(url)
        article.download()
        article.parse()
        
        # Extract NLP features
        try:
            article.nlp()
        except:
            pass
        
        raw_text = article.text
        
        # Apply comprehensive cleaning
        cleaned_text = clean_article_text(raw_text)
        
        return {
            'url': original_url,
            'resolved_url': url,
            'title': article.title,
            'authors': ', '.join(article.authors) if article.authors else 'Unknown',
            'publish_date': str(article.publish_date) if article.publish_date else None,
            'raw_content': raw_text,
            'cleaned_content': cleaned_text,
            'top_image': article.top_image,
            'keywords': ', '.join(article.keywords) if hasattr(article, 'keywords') and article.keywords else '',
            'extraction_status': 'Success'
        }
    
    except Exception as e:
        return {
            'url': original_url if 'original_url' in locals() else url,
            'resolved_url': url if 'original_url' in locals() else None,
            'title': 'Error',
            'authors': '',
            'publish_date': None,
            'raw_content': '',
            'cleaned_content': '',
            'top_image': '',
            'keywords': '',
            'extraction_status': f'Failed: {str(e)}'
        }


def scrap_news(query: str, count: int) -> Dict[str, List[Dict[str, Any]]]:
    """
    Search for news articles using PyGoogleNews and extract full content
    
    Args:
        query: Search query string
        count: Maximum number of articles to retrieve
        
    Returns:
        Dict with 'articles' key containing list of article dicts with fields:
        - title: Article title
        - author: Article author(s)
        - link: Article URL
        - description: First 200 chars of cleaned content
        - content: Full cleaned article content
        - query: Search query used
    """
    try:
        # Get rate limit from settings (default 1 second)
        rate_limit = getattr(settings, 'news_scraper_rate_limit', 1.0)
        
        gn = GoogleNews(lang='en', country='US')
        
        print(f"[News Scraper V2] Searching for: '{query}' (max {count} results)")
        search_result = gn.search(query)
        
        articles = []
        entries = search_result.get('entries', [])[:count]
        
        print(f"[News Scraper V2] Found {len(entries)} articles. Extracting content...")
        
        for idx, entry in enumerate(entries, 1):
            url = entry.link
            print(f"[News Scraper V2] [{idx}/{len(entries)}] Processing: {entry.title[:60]}...")
            
            article_data = extract_full_article(url)
            
            # Transform to expected API format
            if article_data['extraction_status'] == 'Success':
                # Generate description from first 200 chars of cleaned content
                description = article_data['cleaned_content'][:200] + '...' if len(article_data['cleaned_content']) > 200 else article_data['cleaned_content']
                
                articles.append({
                    'title': article_data['title'],
                    'author': article_data['authors'],
                    'link': article_data['resolved_url'] or article_data['url'],
                    'description': description,
                    'content': article_data['cleaned_content'],
                    'query': query
                })
                
                print(f"[News Scraper V2]   ✓ Extracted {len(article_data['cleaned_content'])} chars")
            else:
                print(f"[News Scraper V2]   ✗ {article_data['extraction_status']}")
            
            # Rate limiting between requests
            if idx < len(entries):  # Don't sleep after last article
                time.sleep(rate_limit)
        
        print(f"[News Scraper V2] Successfully extracted {len(articles)}/{len(entries)} articles")
        
        return {'articles': articles}
    
    except Exception as e:
        print(f"[News Scraper V2] Failed to fetch articles: {e}")
        # Return empty dict with articles key (consistent with error handling)
        return {'articles': []}
