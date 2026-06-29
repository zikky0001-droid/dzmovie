# ============================================
# MOVIEBOX MIRROR HOSTS CONFIGURATION
# ============================================
import os
os.environ['MOVIEBOX_API_HOST_V1'] = 'h5.aoneroom.com'
os.environ['MOVIEBOX_API_HOST_V2'] = 'h5-api.aoneroom.com'
os.environ['MOVIEBOX_API_HOST_V3'] = 'h5-api.aoneroom.com'
# ============================================

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Any, Dict
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(
    title="DZMovie API",
    description="MovieBox API wrapper for searching and streaming movies & TV series",
    version="1.0.0"
)

# Add CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# MOVIEBOX IMPORT - CORRECT IMPORTS
# ============================================
MOVIEBOX_AVAILABLE = False
client_v1 = None
client_v2 = None
client_v3 = None

try:
    # V1 - MovieAuto for quick downloads
    from moviebox_api.v1 import MovieAuto, Search, Session, SubjectType
    from moviebox_api.v1.download import MediaFileDownloader, CaptionFileDownloader
    
    client_v1 = MovieAuto()
    MOVIEBOX_AVAILABLE = True
    logger.info("✅ MovieBox V1 loaded successfully")
    
    # Try V2
    try:
        from moviebox_api.v2 import MovieAuto as MovieAutoV2
        client_v2 = MovieAutoV2()
        logger.info("✅ MovieBox V2 loaded successfully")
    except ImportError:
        logger.info("ℹ️ V2 not available, using V1 for all operations")
    
    # Try V3
    try:
        from moviebox_api.v3 import MovieAuto as MovieAutoV3
        client_v3 = MovieAutoV3()
        logger.info("✅ MovieBox V3 loaded successfully")
    except ImportError:
        logger.info("ℹ️ V3 not available")
        
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

class SeriesResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

# ============================================
# CACHE MANAGEMENT
# ============================================

cache: Dict[str, tuple] = {}
CACHE_DURATION = 300  # 5 minutes

def get_cache_key(*args, **kwargs) -> str:
    """Generate a cache key from arguments"""
    key_parts = [str(arg) for arg in args]
    key_parts.extend([f"{k}={v}" for k, v in sorted(kwargs.items())])
    return "_".join(key_parts)

def get_from_cache(key: str) -> Optional[Any]:
    """Get cached data if valid"""
    if key in cache:
        data, timestamp = cache[key]
        if (datetime.now() - timestamp).seconds < CACHE_DURATION:
            logger.info(f"✅ Cache hit: {key[:50]}...")
            return data
        else:
            del cache[key]
    return None

def set_cache(key: str, data: Any) -> None:
    """Set data in cache"""
    cache[key] = (data, datetime.now())
    logger.info(f"📝 Cache set: {key[:50]}...")

# ============================================
# ROOT ENDPOINT
# ============================================

@app.get("/")
async def root():
    """Welcome endpoint"""
    return {
        "name": "DZMovie API",
        "version": "1.0.0",
        "status": "running" if MOVIEBOX_AVAILABLE else "degraded",
        "moviebox_available": MOVIEBOX_AVAILABLE,
        "mirrors": {
            "v1": os.environ.get('MOVIEBOX_API_HOST_V1', 'h5.aoneroom.com'),
            "v2": os.environ.get('MOVIEBOX_API_HOST_V2', 'h5-api.aoneroom.com'),
            "v3": os.environ.get('MOVIEBOX_API_HOST_V3', 'h5-api.aoneroom.com')
        },
        "endpoints": [
            {"path": "/", "method": "GET", "description": "API information"},
            {"path": "/health", "method": "GET", "description": "Health check"},
            {"path": "/search", "method": "GET", "description": "Search movies/series", "params": ["query", "version"]},
            {"path": "/movie", "method": "GET", "description": "Get movie details", "params": ["title", "quality", "version"]},
            {"path": "/series", "method": "GET", "description": "Get TV series episode", "params": ["title", "season", "episode", "version"]},
            {"path": "/home", "method": "GET", "description": "Homepage content"},
            {"path": "/mirrors", "method": "GET", "description": "Available mirrors"},
            {"path": "/cache-info", "method": "GET", "description": "Cache information"},
            {"path": "/clear-cache", "method": "POST", "description": "Clear cache"}
        ],
        "examples": {
            "search": "/search?query=avatar",
            "movie": "/movie?title=avatar&quality=1080p",
            "series": "/series?title=game%20of%20thrones&season=1&episode=1"
        }
    }

# ============================================
# HEALTH CHECK
# ============================================

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy" if MOVIEBOX_AVAILABLE else "degraded",
        "timestamp": datetime.now().isoformat(),
        "moviebox_available": MOVIEBOX_AVAILABLE,
        "uptime": "running",
        "cache_size": len(cache)
    }

# ============================================
# SEARCH ENDPOINT - USING V1
# ============================================

@app.get("/search", response_model=SearchResponse)
async def search(
    query: str = Query(..., description="Search term (e.g., avatar, game of thrones)"),
    version: str = Query("v1", description="API version: v1, v2, or v3")
):
    """
    Search for movies and TV series
    
    Example: /search?query=avatar&version=v1
    """
    if not MOVIEBOX_AVAILABLE:
        return SearchResponse(
            success=False,
            error="MovieBox API not available. Please check installation."
        )
    
    cache_key = get_cache_key("search", version, query.lower())
    cached = get_from_cache(cache_key)
    if cached:
        return cached
    
    try:
        logger.info(f"🔍 Searching for: {query} using version {version}")
        
        results = []
        
        if version == "v1" or version == "v2" or version == "v3":
            # Use V1 Search for all versions (most reliable)
            from moviebox_api.v1 import Search, Session, SubjectType
            
            session = Session()
            search_obj = Search(
                session=session,
                query=query,
                subject_type=SubjectType.MOVIES
            )
            
            search_results = await search_obj.get_content_model()
            
            # Extract items from search results
            if hasattr(search_results, 'items') and search_results.items:
                for item in search_results.items[:20]:  # Limit to 20 results
                    results.append({
                        'title': getattr(item, 'title', 'Unknown'),
                        'year': getattr(item, 'year', ''),
                        'slug': getattr(item, 'slug', ''),
                        'id': getattr(item, 'id', ''),
                        'poster': getattr(item, 'poster', ''),
                        'type': 'movie'
                    })
            elif hasattr(search_results, 'results'):
                for item in search_results.results[:20]:
                    if isinstance(item, dict):
                        results.append(item)
                    else:
                        results.append({
                            'title': getattr(item, 'title', 'Unknown'),
                            'slug': getattr(item, 'slug', '')
                        })
        
        response = SearchResponse(
            success=True,
            results=results
        )
        
        set_cache(cache_key, response)
        return response
        
    except Exception as e:
        logger.error(f"❌ Search error: {str(e)}")
        return SearchResponse(
            success=False,
            error=f"Search failed: {str(e)}"
        )

# ============================================
# MOVIE DETAILS ENDPOINT - USING V1 MovieAuto
# ============================================

@app.get("/movie", response_model=MovieResponse)
async def get_movie(
    title: str = Query(..., description="Movie title"),
    quality: str = Query("best", description="Quality: best, 1080p, 720p, 480p, 360p, worst"),
    version: str = Query("v1", description="API version: v1, v2, or v3")
):
    """
    Get movie details and download URL
    
    Example: /movie?title=avatar&quality=1080p&version=v1
    """
    if not MOVIEBOX_AVAILABLE:
        return MovieResponse(
            success=False,
            error="MovieBox API not available. Please check installation."
        )
    
    cache_key = get_cache_key("movie", version, title.lower(), quality)
    cached = get_from_cache(cache_key)
    if cached:
        return cached
    
    try:
        logger.info(f"🎬 Fetching movie: {title} (quality: {quality}, version: {version})")
        
        # Use V1 MovieAuto for all versions
        from moviebox_api.v1 import MovieAuto
        
        movie_auto = MovieAuto()
        
        # Download the movie (this will prompt for selection, but we'll handle it)
        # We need to get the URL without actually downloading
        
        # Alternative: Use Search and MovieDetails to get URL
        from moviebox_api.v1 import Search, Session, SubjectType, MovieDetails
        from moviebox_api.v1.download import MediaFileDownloader
        
        session = Session()
        search_obj = Search(
            session=session,
            query=title,
            subject_type=SubjectType.MOVIES
        )
        
        search_results = await search_obj.get_content_model()
        
        if not search_results or not search_results.items:
            return MovieResponse(
                success=False,
                error=f"No results found for '{title}'"
            )
        
        # Get first result
        target_movie = search_results.items[0]
        
        # Get movie details
        movie_details = MovieDetails(target_movie, session)
        details = await movie_details.get_content_model()
        
        # Get downloadable files
        from moviebox_api.v1 import DownloadableMovieFilesDetail
        downloadable = DownloadableMovieFilesDetail(session, details)
        files_detail = await downloadable.get_content_model()
        
        # Get best quality file
        best_file = files_detail.best_media_file
        
        movie_url = getattr(best_file, 'url', None)
        movie_quality = getattr(best_file, 'quality', quality)
        movie_title = getattr(target_movie, 'title', title)
        
        # Get subtitle if available
        subtitle_url = None
        if hasattr(files_detail, 'english_subtitle_file'):
            subtitle = files_detail.english_subtitle_file
            subtitle_url = getattr(subtitle, 'url', None)
        elif hasattr(files_detail, 'captions') and files_detail.captions:
            for cap in files_detail.captions:
                if 'english' in getattr(cap, 'language', '').lower():
                    subtitle_url = getattr(cap, 'url', None)
                    break
        
        response = MovieResponse(
            success=True,
            title=movie_title,
            quality=movie_quality,
            url=movie_url,
            subtitle_url=subtitle_url
        )
        
        set_cache(cache_key, response)
        return response
        
    except Exception as e:
        logger.error(f"❌ Movie fetch error: {str(e)}")
        return MovieResponse(
            success=False,
            error=f"Failed to fetch movie: {str(e)}"
        )

# ============================================
# TV SERIES ENDPOINT - USING V1
# ============================================

@app.get("/series", response_model=SeriesResponse)
async def get_series(
    title: str = Query(..., description="Series title"),
    season: int = Query(..., description="Season number", ge=1),
    episode: int = Query(..., description="Episode number", ge=1),
    quality: str = Query("best", description="Quality: best, 1080p, 720p, 480p, 360p, worst"),
    version: str = Query("v1", description="API version: v1, v2, or v3")
):
    """
    Get TV series episode details
    
    Example: /series?title=game%20of%20thrones&season=1&episode=1&version=v1
    """
    if not MOVIEBOX_AVAILABLE:
        return SeriesResponse(
            success=False,
            error="MovieBox API not available. Please check installation."
        )
    
    cache_key = get_cache_key("series", version, title.lower(), season, episode, quality)
    cached = get_from_cache(cache_key)
    if cached:
        return cached
    
    try:
        logger.info(f"📺 Fetching series: {title} S{season}E{episode}")
        
        # Use V1 TV Series search
        from moviebox_api.v1 import Search, Session, SubjectType, MovieDetails
        
        session = Session()
        search_obj = Search(
            session=session,
            query=title,
            subject_type=SubjectType.TV_SERIES
        )
        
        search_results = await search_obj.get_content_model()
        
        if not search_results or not search_results.items:
            return SeriesResponse(
                success=False,
                error=f"No results found for '{title}'"
            )
        
        # Get first result
        target_series = search_results.items[0]
        
        # Get series details
        series_details = MovieDetails(target_series, session)
        details = await series_details.get_content_model()
        
        # Parse seasons and episodes
        # The structure might be different, so we'll construct a response
        response_data = {
            'title': getattr(target_series, 'title', title),
            'season': season,
            'episode': episode,
            'quality': quality,
            'url': None,
            'subtitle_url': None
        }
        
        # Try to get download info if available
        try:
            from moviebox_api.v1 import DownloadableMovieFilesDetail
            downloadable = DownloadableMovieFilesDetail(session, details)
            files_detail = await downloadable.get_content_model()
            
            best_file = files_detail.best_media_file
            response_data['url'] = getattr(best_file, 'url', None)
            
            if hasattr(files_detail, 'english_subtitle_file'):
                subtitle = files_detail.english_subtitle_file
                response_data['subtitle_url'] = getattr(subtitle, 'url', None)
        except:
            pass
        
        response = SeriesResponse(
            success=True,
            data=response_data
        )
        
        set_cache(cache_key, response)
        return response
        
    except Exception as e:
        logger.error(f"❌ Series fetch error: {str(e)}")
        return SeriesResponse(
            success=False,
            error=f"Failed to fetch series: {str(e)}"
        )

# ============================================
# HOMEPAGE CONTENT ENDPOINT
# ============================================

@app.get("/home")
async def get_homepage(
    version: str = Query("v1", description="API version: v1, v2, or v3")
):
    """
    Get homepage content (banners, trending, popular, etc.)
    
    Example: /home?version=v1
    """
    if not MOVIEBOX_AVAILABLE:
        return {"success": False, "error": "MovieBox API not available"}
    
    cache_key = get_cache_key("homepage", version)
    cached = get_from_cache(cache_key)
    if cached:
        return cached
    
    try:
        logger.info(f"🏠 Fetching homepage content")
        
        # Use V1 homepage
        from moviebox_api.v1 import HomepageContent
        
        homepage = HomepageContent()
        content = await homepage.get_content_model()
        
        # Convert to dict
        content_dict = {}
        if hasattr(content, '__dict__'):
            content_dict = {
                'banners': getattr(content, 'banners', []),
                'trending': getattr(content, 'trending', []),
                'popular': getattr(content, 'popular', []),
                'sections': getattr(content, 'sections', {})
            }
        
        response = {
            "success": True,
            "version": version,
            "content": content_dict
        }
        
        set_cache(cache_key, response)
        return response
        
    except Exception as e:
        logger.error(f"❌ Homepage fetch error: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to fetch homepage: {str(e)}"
        }

# ============================================
# MIRRORS ENDPOINT
# ============================================

@app.get("/mirrors")
async def get_mirrors():
    """
    Get available mirror hosts
    
    Example: /mirrors
    """
    return {
        "success": True,
        "mirrors": {
            "v1": os.environ.get('MOVIEBOX_API_HOST_V1', 'h5.aoneroom.com'),
            "v2": os.environ.get('MOVIEBOX_API_HOST_V2', 'h5-api.aoneroom.com'),
            "v3": os.environ.get('MOVIEBOX_API_HOST_V3', 'h5-api.aoneroom.com')
        },
        "all_mirrors": [
            "h5.aoneroom.com",
            "h5-api.aoneroom.com",
            "moviebox.ph"
        ]
    }

# ============================================
# SEARCH SUGGESTIONS ENDPOINT
# ============================================

@app.get("/suggest")
async def get_suggestions(
    query: str = Query(..., description="Search term for suggestions")
):
    """
    Get search suggestions/autocomplete
    
    Example: /suggest?query=ava
    """
    if not MOVIEBOX_AVAILABLE:
        return {"success": False, "error": "MovieBox API not available"}
    
    cache_key = get_cache_key("suggest", query.lower())
    cached = get_from_cache(cache_key)
    if cached:
        return cached
    
    try:
        logger.info(f"💡 Getting suggestions for: {query}")
        
        # Use V1 search to get suggestions
        from moviebox_api.v1 import Search, Session, SubjectType
        
        session = Session()
        search_obj = Search(
            session=session,
            query=query,
            subject_type=SubjectType.MOVIES
        )
        
        search_results = await search_obj.get_content_model()
        
        suggestions = []
        if hasattr(search_results, 'items') and search_results.items:
            suggestions = [getattr(item, 'title', '') for item in search_results.items[:5]]
        
        response = {
            "success": True,
            "query": query,
            "suggestions": suggestions
        }
        
        set_cache(cache_key, response)
        return response
        
    except Exception as e:
        logger.error(f"❌ Suggestions error: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to get suggestions: {str(e)}"
        }

# ============================================
# CACHE MANAGEMENT ENDPOINTS
# ============================================

@app.get("/cache-info")
async def cache_info():
    """Get cache information"""
    return {
        "cache_size": len(cache),
        "cache_keys": list(cache.keys()),
        "max_duration_seconds": CACHE_DURATION
    }

@app.post("/clear-cache")
async def clear_cache():
    """Clear the API cache"""
    global cache
    cache_size = len(cache)
    cache.clear()
    return {
        "success": True, 
        "message": f"Cache cleared ({cache_size} items removed)",
        "timestamp": datetime.now().isoformat()
    }

# ============================================
# ERROR HANDLING
# ============================================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": f"Internal server error: {str(exc)}"
        }
    )

# ============================================
# RUN THE APP
# ============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )


