# ============================================
# MOVIEBOX V1 ONLY - SIMPLIFIED API
# ============================================
import os
os.environ['MOVIEBOX_API_HOST'] = 'h5.aoneroom.com'
# ============================================

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(
    title="DZMovie API",
    description="MovieBox V1 API wrapper",
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
MOVIEBOX_AVAILABLE = False

try:
    from moviebox_api.v1 import (
        MovieAuto,
        Search,
        Session,
        SubjectType,
        MovieDetails,
        TVSeriesDetails,
        HomepageContent,
        DownloadableMovieFilesDetail,
        DownloadableTVSeriesFilesDetail,
    )
    from moviebox_api.v1.download import MediaFileDownloader, CaptionFileDownloader
    
    MOVIEBOX_AVAILABLE = True
    logger.info("✅ MovieBox V1 loaded successfully")
except ImportError as e:
    logger.error(f"❌ MovieBox import failed: {e}")
    MOVIEBOX_AVAILABLE = False

# ============================================
# RESPONSE MODELS
# ============================================

class MovieResponse(BaseModel):
    success: bool
    title: Optional[str] = None
    quality: Optional[str] = None
    url: Optional[str] = None
    subtitle_url: Optional[str] = None
    error: Optional[str] = None

class SearchResponse(BaseModel):
    success: bool
    results: Optional[List[Dict[str, Any]]] = None
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
# ROOT ENDPOINT
# ============================================

@app.get("/")
async def root():
    return {
        "name": "DZMovie API",
        "version": "1.0.0",
        "status": "running" if MOVIEBOX_AVAILABLE else "degraded",
        "moviebox_available": MOVIEBOX_AVAILABLE,
        "mirror": os.environ.get('MOVIEBOX_API_HOST', 'h5.aoneroom.com'),
        "endpoints": {
            "search": "/search?query=avatar",
            "movie": "/movie?title=avatar&quality=1080p",
            "series": "/series?title=merlin&season=1&episode=1",
            "home": "/home",
            "popular": "/popular",
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
        "moviebox_available": MOVIEBOX_AVAILABLE,
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
        
        response = SearchResponse(success=True, results=results)
        set_cache(cache_key, response)
        return response
        
    except Exception as e:
        logger.error(f"❌ Search error: {str(e)}")
        return SearchResponse(success=False, error=str(e))

# ============================================
# MOVIE ENDPOINT
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
        
        session = Session()
        
        # Search for the movie
        search_obj = Search(
            session=session,
            query=title,
            subject_type=SubjectType.MOVIES
        )
        search_results = await search_obj.get_content_model()
        
        if not search_results or not search_results.items:
            return MovieResponse(success=False, error=f"No results found for '{title}'")
        
        target_movie = search_results.items[0]
        
        # Get movie details
        movie_details = MovieDetails(target_movie, session)
        details = await movie_details.get_content_model()
        
        # Get downloadable files
        downloadable = DownloadableMovieFilesDetail(session, details)
        files_detail = await downloadable.get_content_model()
        
        # Get best quality file
        if quality == "best":
            media_file = files_detail.best_media_file
        else:
            # Find specific quality
            media_file = None
            for file in files_detail.downloads:
                if hasattr(file, 'quality') and file.quality == quality:
                    media_file = file
                    break
            if not media_file:
                media_file = files_detail.best_media_file
        
        # Get subtitle
        subtitle_url = None
        if hasattr(files_detail, 'english_subtitle_file'):
            subtitle = files_detail.english_subtitle_file
            subtitle_url = getattr(subtitle, 'url', None)
        
        response = MovieResponse(
            success=True,
            title=getattr(target_movie, 'title', title),
            quality=getattr(media_file, 'quality', quality) if media_file else quality,
            url=getattr(media_file, 'url', None) if media_file else None,
            subtitle_url=subtitle_url
        )
        
        set_cache(cache_key, response)
        return response
        
    except Exception as e:
        logger.error(f"❌ Movie error: {str(e)}")
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
        
        # Get series details
        series_details = TVSeriesDetails(target_series, session)
        details = await series_details.get_content_model()
        
        # Get downloadable files for specific episode
        downloadable = DownloadableTVSeriesFilesDetail(session, details)
        files_detail = await downloadable.get_content_model(
            season=season,
            episode=episode
        )
        
        # Get best quality file
        media_file = files_detail.best_media_file
        
        # Get subtitle
        subtitle_url = None
        if hasattr(files_detail, 'english_subtitle_file'):
            subtitle = files_detail.english_subtitle_file
            subtitle_url = getattr(subtitle, 'url', None)
        
        response = {
            "success": True,
            "data": {
                "title": getattr(target_series, 'title', title),
                "season": season,
                "episode": episode,
                "quality": getattr(media_file, 'quality', quality) if media_file else quality,
                "url": getattr(media_file, 'url', None) if media_file else None,
                "subtitle_url": subtitle_url
            }
        }
        
        set_cache(cache_key, response)
        return response
        
    except Exception as e:
        logger.error(f"❌ Series error: {str(e)}")
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
        
        homepage = HomepageContent()
        content = await homepage.get_content_model()
        
        # Convert to dict
        result = {
            "success": True,
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
        
    except Exception as e:
        logger.error(f"❌ Homepage error: {str(e)}")
        return {"success": False, "error": str(e)}

# ============================================
# POPULAR SEARCH ENDPOINT
# ============================================

@app.get("/popular")
async def get_popular():
    if not MOVIEBOX_AVAILABLE:
        return {"success": False, "error": "MovieBox API not available"}
    
    cache_key = "popular"
    cached = get_from_cache(cache_key)
    if cached:
        return cached
    
    try:
        logger.info("🔥 Fetching popular searches")
        
        from moviebox_api.v1 import PopularSearch
        
        popular = PopularSearch()
        results = await popular.get_content_model()
        
        # Convert to list
        items = []
        if hasattr(results, 'items'):
            for item in results.items:
                items.append({
                    "title": getattr(item, 'title', ''),
                    "type": getattr(item, 'type', ''),
                    "url": getattr(item, 'url', '')
                })
        
        response = {"success": True, "results": items}
        set_cache(cache_key, response)
        return response
        
    except Exception as e:
        logger.error(f"❌ Popular error: {str(e)}")
        return {"success": False, "error": str(e)}

# ============================================
# MIRRORS ENDPOINT
# ============================================

@app.get("/mirrors")
async def get_mirrors():
    if not MOVIEBOX_AVAILABLE:
        return {"success": False, "error": "MovieBox API not available"}
    
    try:
        from moviebox_api.v1 import MirrorHosts
        
        mirrors = MirrorHosts()
        results = await mirrors.get_content()
        
        return {
            "success": True,
            "current": os.environ.get('MOVIEBOX_API_HOST', 'h5.aoneroom.com'),
            "mirrors": results if isinstance(results, list) else [results]
        }
        
    except Exception as e:
        logger.error(f"❌ Mirrors error: {str(e)}")
        return {"success": False, "error": str(e)}

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
