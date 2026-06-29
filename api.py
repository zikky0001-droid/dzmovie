# ============================================
# MOVIEBOX API - V1 + Custom Scraper
# ============================================
import os
os.environ['MOVIEBOX_API_HOST'] = 'h5.aoneroom.com'
os.environ['MOVIEBOX_API_HOST_V2'] = 'h5-api.aoneroom.com'
# ============================================

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
import re
import json

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(
    title="DZMovie API",
    description="MovieBox API - V1 with custom scraper",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# MOVIEBOX V1 IMPORTS
# ============================================
V1_AVAILABLE = False

try:
    from moviebox_api.v1 import (
        MovieAuto,
        Search,
        Session,
        SubjectType,
        MovieDetails,
        TVSeriesDetails,
        DownloadableMovieFilesDetail,
        DownloadableTVSeriesFilesDetail,
        HomepageContent,
    )
    from moviebox_api.v1.download import MediaFileDownloader, CaptionFileDownloader
    V1_AVAILABLE = True
    logger.info("✅ MovieBox V1 loaded successfully")
except ImportError as e:
    logger.warning(f"⚠️ V1 import failed: {e}")

MOVIEBOX_AVAILABLE = V1_AVAILABLE

# ============================================
# CUSTOM HEADERS
# ============================================

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Referer': 'https://moviebox.ph/',
    'Origin': 'https://moviebox.ph',
    'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-site',
    'Sec-Fetch-User': '?1',
    'Connection': 'keep-alive',
}

# ============================================
# RESPONSE MODELS
# ============================================

class MovieResponse(BaseModel):
    success: bool
    title: Optional[str] = None
    quality: Optional[str] = None
    url: Optional[str] = None
    subtitle_url: Optional[str] = None
    version_used: Optional[str] = None
    error: Optional[str] = None

class SearchResponse(BaseModel):
    success: bool
    results: Optional[List[Dict[str, Any]]] = None
    version_used: Optional[str] = None
    error: Optional[str] = None

# ============================================
# CACHE
# ============================================

cache: Dict[str, tuple] = {}
CACHE_DURATION = 300

def get_cache_key(*args, **kwargs) -> str:
    key_parts = [str(arg) for arg in args]
    key_parts.extend([f"{k}={v}" for k, v in sorted(kwargs.items())])
    return "_".join(key_parts)

def get_from_cache(key: str) -> Optional[Any]:
    if key in cache:
        data, timestamp = cache[key]
        if (datetime.now() - timestamp).seconds < CACHE_DURATION:
            return data
        del cache[key]
    return None

def set_cache(key: str, data: Any) -> None:
    cache[key] = (data, datetime.now())

# ============================================
# CUSTOM SCRAPER FUNCTIONS
# ============================================

async def get_movie_download_url(slug: str, movie_id: str, quality: str = "best") -> Dict[str, Any]:
    """Custom scraper to get download URL using the detail page"""
    try:
        # First try to get from the detail page
        detail_url = f"https://moviebox.ph/detail/{slug}"
        logger.info(f"📄 Scraping detail page: {detail_url}")
        
        async with httpx.AsyncClient(headers=HEADERS, timeout=30.0, follow_redirects=True) as client:
            response = await client.get(detail_url)
            
            if response.status_code != 200:
                return {"success": False, "error": f"Failed to fetch detail page: {response.status_code}"}
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for the download URL in the page
            # Try to find video source in player
            video_sources = soup.find_all('source')
            for source in video_sources:
                src = source.get('src', '')
                if src and '.mp4' in src:
                    return {
                        "success": True,
                        "url": src,
                        "quality": quality
                    }
            
            # Try to find in script tags
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string:
                    # Look for video URLs in JavaScript
                    matches = re.findall(r'https?://[^\s"\']+\.mp4[^\s"\']*', script.string)
                    if matches:
                        return {
                            "success": True,
                            "url": matches[0],
                            "quality": quality
                        }
                    
                    # Look for JSON data
                    try:
                        json_data = re.search(r'({.*"video".*})', script.string)
                        if json_data:
                            data = json.loads(json_data.group(1))
                            if 'video' in data:
                                videos = data['video']
                                if isinstance(videos, dict):
                                    for q in ['1080p', '720p', '480p', '360p']:
                                        if q in videos and videos[q]:
                                            return {
                                                "success": True,
                                                "url": videos[q],
                                                "quality": q
                                            }
                    except:
                        pass
            
            return {"success": False, "error": "No video URL found in detail page"}
            
    except Exception as e:
        logger.error(f"❌ Scraper error: {e}")
        return {"success": False, "error": str(e)}

# ============================================
# ROOT ENDPOINT
# ============================================

@app.get("/")
async def root():
    return {
        "name": "DZMovie API",
        "version": "1.0.0",
        "status": "running" if MOVIEBOX_AVAILABLE else "degraded",
        "versions": {"v1": V1_AVAILABLE},
        "mirror": os.environ.get('MOVIEBOX_API_HOST', 'h5.aoneroom.com'),
        "endpoints": {
            "search": "/search?query=avatar",
            "movie": "/movie?title=avatar&quality=1080p",
            "series": "/series?title=merlin&season=1&episode=1",
            "home": "/home",
            "mirrors": "/mirrors"
        }
    }

# ============================================
# HEALTH CHECK
# ============================================

@app.get("/health")
async def health():
    return {
        "status": "healthy" if MOVIEBOX_AVAILABLE else "degraded",
        "timestamp": datetime.now().isoformat(),
        "versions": {"v1": V1_AVAILABLE},
        "cache_size": len(cache)
    }

# ============================================
# SEARCH ENDPOINT
# ============================================

@app.get("/search", response_model=SearchResponse)
async def search(
    query: str = Query(..., description="Search term"),
    subject_type: str = Query("movies", description="movies, tv_series, anime, music, education")
):
    if not MOVIEBOX_AVAILABLE:
        return SearchResponse(success=False, error="MovieBox API not available")
    
    cache_key = get_cache_key("search", query.lower(), subject_type)
    cached = get_from_cache(cache_key)
    if cached:
        return cached
    
    try:
        logger.info(f"🔍 Searching for: {query} ({subject_type})")
        
        # Map subject type
        type_map = {
            "movies": SubjectType.MOVIES,
            "tv_series": SubjectType.TV_SERIES,
            "anime": SubjectType.ANIME,
            "music": SubjectType.MUSIC,
            "education": SubjectType.EDUCATION,
        }
        subject = type_map.get(subject_type, SubjectType.MOVIES)
        
        session = Session()
        search_obj = Search(
            session=session,
            query=query,
            subject_type=subject
        )
        
        search_results = await search_obj.get_content_model()
        
        results = []
        if hasattr(search_results, 'items') and search_results.items:
            for item in search_results.items[:20]:
                results.append({
                    'title': getattr(item, 'title', 'Unknown'),
                    'year': getattr(item, 'year', ''),
                    'slug': getattr(item, 'slug', ''),
                    'id': getattr(item, 'id', ''),
                    'poster': getattr(item, 'poster', ''),
                    'type': subject_type
                })
        
        response = SearchResponse(success=True, results=results, version_used="v1")
        set_cache(cache_key, response)
        return response
        
    except Exception as e:
        logger.error(f"❌ Search error: {str(e)}")
        return SearchResponse(success=False, error=str(e))

# ============================================
# MOVIE ENDPOINT - V1 + Custom Scraper
# ============================================

@app.get("/movie", response_model=MovieResponse)
async def get_movie(
    title: str = Query(..., description="Movie title"),
    quality: str = Query("best", description="best, 1080p, 720p, 480p, 360p, worst")
):
    if not MOVIEBOX_AVAILABLE:
        return MovieResponse(success=False, error="MovieBox API not available")
    
    cache_key = get_cache_key("movie", title.lower(), quality)
    cached = get_from_cache(cache_key)
    if cached:
        return cached
    
    try:
        logger.info(f"🎬 Fetching movie: {title} ({quality})")
        
        # Step 1: Search for the movie using V1
        session = Session()
        search_obj = Search(
            session=session,
            query=title,
            subject_type=SubjectType.MOVIES
        )
        search_results = await search_obj.get_content_model()
        
        if not search_results or not search_results.items:
            return MovieResponse(success=False, error=f"No results found for '{title}'")
        
        target_movie = search_results.items[0]
        movie_title = getattr(target_movie, 'title', title)
        movie_slug = getattr(target_movie, 'slug', '')
        movie_id = getattr(target_movie, 'id', '')
        
        # Step 2: Get movie details using V1
        movie_details = MovieDetails(target_movie, session)
        details = await movie_details.get_content_model()
        
        # Step 3: Try to get download URL using custom scraper
        scraper_result = await get_movie_download_url(movie_slug, movie_id, quality)
        
        if scraper_result.get("success"):
            response = MovieResponse(
                success=True,
                title=movie_title,
                quality=scraper_result.get("quality", quality),
                url=scraper_result.get("url"),
                subtitle_url=None,  # Will try to get later
                version_used="v1+custom"
            )
            set_cache(cache_key, response)
            return response
        
        # Step 4: Fallback - Try to get from downloadable files (might still 403)
        try:
            downloadable = DownloadableMovieFilesDetail(session, details)
            files_detail = await downloadable.get_content_model()
            
            if quality == "best":
                media_file = files_detail.best_media_file
            else:
                media_file = None
                for file in files_detail.downloads:
                    if hasattr(file, 'quality') and file.quality == quality:
                        media_file = file
                        break
                if not media_file:
                    media_file = files_detail.best_media_file
            
            subtitle_url = None
            if hasattr(files_detail, 'english_subtitle_file'):
                subtitle = files_detail.english_subtitle_file
                subtitle_url = getattr(subtitle, 'url', None)
            
            response = MovieResponse(
                success=True,
                title=movie_title,
                quality=getattr(media_file, 'quality', quality) if media_file else quality,
                url=getattr(media_file, 'url', None) if media_file else None,
                subtitle_url=subtitle_url,
                version_used="v1"
            )
            
            set_cache(cache_key, response)
            return response
            
        except Exception as e:
            logger.warning(f"⚠️ V1 download failed: {e}")
            
            # Step 5: Final fallback - try to get from detail page directly using HTML
            try:
                detail_url = f"https://moviebox.ph/detail/{movie_slug}"
                async with httpx.AsyncClient(headers=HEADERS, timeout=30.0) as client:
                    resp = await client.get(detail_url)
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, 'html.parser')
                        # Find iframe or video source
                        iframe = soup.find('iframe')
                        if iframe and iframe.get('src'):
                            src = iframe.get('src')
                            if src.startswith('//'):
                                src = 'https:' + src
                            response = MovieResponse(
                                success=True,
                                title=movie_title,
                                quality=quality,
                                url=src,
                                version_used="custom"
                            )
                            set_cache(cache_key, response)
                            return response
            except:
                pass
            
            return MovieResponse(
                success=False,
                error="Could not extract video URL. The site may have anti-scraping measures."
            )
        
    except Exception as e:
        logger.error(f"❌ Movie fetch error: {str(e)}")
        return MovieResponse(success=False, error=str(e))

# ============================================
# SERIES ENDPOINT
# ============================================

@app.get("/series")
async def get_series(
    title: str = Query(..., description="Series title"),
    season: int = Query(..., description="Season number", ge=1),
    episode: int = Query(..., description="Episode number", ge=1),
    quality: str = Query("best", description="best, 1080p, 720p, 480p, 360p, worst")
):
    if not MOVIEBOX_AVAILABLE:
        return {"success": False, "error": "MovieBox API not available"}
    
    cache_key = get_cache_key("series", title.lower(), season, episode, quality)
    cached = get_from_cache(cache_key)
    if cached:
        return cached
    
    try:
        logger.info(f"📺 Fetching series: {title} S{season}E{episode}")
        
        session = Session()
        
        # Search for the series
        search_obj = Search(
            session=session,
            query=title,
            subject_type=SubjectType.TV_SERIES
        )
        search_results = await search_obj.get_content_model()
        
        if not search_results or not search_results.items:
            return {"success": False, "error": f"No results found for '{title}'"}
        
        target_series = search_results.items[0]
        series_title = getattr(target_series, 'title', title)
        series_slug = getattr(target_series, 'slug', '')
        
        # Get series details
        series_details = TVSeriesDetails(target_series, session)
        details = await series_details.get_content_model()
        
        # Try to get downloadable files
        try:
            downloadable = DownloadableTVSeriesFilesDetail(session, details)
            files_detail = await downloadable.get_content_model(
                season=season,
                episode=episode
            )
            
            media_file = files_detail.best_media_file
            
            subtitle_url = None
            if hasattr(files_detail, 'english_subtitle_file'):
                subtitle = files_detail.english_subtitle_file
                subtitle_url = getattr(subtitle, 'url', None)
            
            return {
                "success": True,
                "version_used": "v1",
                "data": {
                    "title": series_title,
                    "season": season,
                    "episode": episode,
                    "quality": getattr(media_file, 'quality', quality) if media_file else quality,
                    "url": getattr(media_file, 'url', None) if media_file else None,
                    "subtitle_url": subtitle_url
                }
            }
        except Exception as e:
            logger.warning(f"⚠️ Series download failed: {e}")
            
            # Fallback: Try to get from detail page
            try:
                detail_url = f"https://moviebox.ph/detail/{series_slug}"
                async with httpx.AsyncClient(headers=HEADERS, timeout=30.0) as client:
                    resp = await client.get(detail_url)
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, 'html.parser')
                        iframe = soup.find('iframe')
                        if iframe and iframe.get('src'):
                            src = iframe.get('src')
                            if src.startswith('//'):
                                src = 'https:' + src
                            return {
                                "success": True,
                                "version_used": "custom",
                                "data": {
                                    "title": series_title,
                                    "season": season,
                                    "episode": episode,
                                    "quality": quality,
                                    "url": src,
                                    "subtitle_url": None
                                }
                            }
            except:
                pass
            
            return {
                "success": False,
                "error": "Could not extract video URL"
            }
        
    except Exception as e:
        logger.error(f"❌ Series fetch error: {str(e)}")
        return {"success": False, "error": str(e)}

# ============================================
# HOMEPAGE ENDPOINT
# ============================================

@app.get("/home")
async def get_homepage():
    if not MOVIEBOX_AVAILABLE:
        return {"success": False, "error": "MovieBox API not available"}
    
    cache_key = "homepage"
    cached = get_from_cache(cache_key)
    if cached:
        return cached
    
    try:
        logger.info("🏠 Fetching homepage content")
        
        try:
            from moviebox_api.v1 import HomepageContent
            homepage = HomepageContent()
            content = await homepage.get_content_model()
            
            result = {
                "success": True,
                "version_used": "v1",
                "content": {
                    "banners": [],
                    "trending": [],
                    "popular": [],
                    "sections": {}
                }
            }
            
            if hasattr(content, 'banners'):
                for banner in content.banners:
                    result["content"]["banners"].append({
                        "title": getattr(banner, 'title', ''),
                        "image": getattr(banner, 'image', ''),
                        "url": getattr(banner, 'url', '')
                    })
            
            if hasattr(content, 'trending'):
                for item in content.trending:
                    result["content"]["trending"].append({
                        "title": getattr(item, 'title', ''),
                        "slug": getattr(item, 'slug', ''),
                        "poster": getattr(item, 'poster', '')
                    })
            
            if hasattr(content, 'popular'):
                for item in content.popular:
                    result["content"]["popular"].append({
                        "title": getattr(item, 'title', ''),
                        "slug": getattr(item, 'slug', ''),
                        "poster": getattr(item, 'poster', '')
                    })
            
            set_cache(cache_key, result)
            return result
            
        except ImportError:
            # Fallback: Scrape homepage directly
            async with httpx.AsyncClient(headers=HEADERS, timeout=30.0) as client:
                resp = await client.get("https://moviebox.ph/")
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    trending = []
                    popular = []
                    
                    # Find trending items
                    for item in soup.find_all('div', class_=re.compile(r'trend|popular')):
                        title_elem = item.find(['h3', 'h2', 'div'], class_=re.compile(r'title|name'))
                        if title_elem:
                            trending.append({"title": title_elem.text.strip()})
                    
                    result = {
                        "success": True,
                        "version_used": "custom",
                        "content": {
                            "banners": [],
                            "trending": trending[:10],
                            "popular": popular[:10],
                            "sections": {}
                        }
                    }
                    set_cache(cache_key, result)
                    return result
        
    except Exception as e:
        logger.error(f"❌ Homepage error: {str(e)}")
        return {"success": False, "error": str(e)}

# ============================================
# MIRRORS ENDPOINT
# ============================================

@app.get("/mirrors")
async def get_mirrors():
    return {
        "success": True,
        "mirrors": ["h5.aoneroom.com", "h5-api.aoneroom.com", "moviebox.ph"],
        "current": os.environ.get('MOVIEBOX_API_HOST', 'h5.aoneroom.com')
    }

# ============================================
# CACHE MANAGEMENT
# ============================================

@app.get("/cache-info")
async def cache_info():
    return {
        "cache_size": len(cache),
        "cache_keys": list(cache.keys()),
        "max_duration_seconds": CACHE_DURATION
    }

@app.post("/clear-cache")
async def clear_cache():
    global cache
    cache_size = len(cache)
    cache.clear()
    return {
        "success": True,
        "message": f"Cache cleared ({cache_size} items removed)"
    }

# ============================================
# ERROR HANDLING
# ============================================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": str(exc)}
    )

# ============================================
# RUN
# ============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)

