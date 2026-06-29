# ============================================
# MOVIEBOX MIRROR HOSTS CONFIGURATION
# ============================================
import os
os.environ['MOVIEBOX_API_HOST_V2'] = 'h5-api.aoneroom.com'
os.environ['MOVIEBOX_API_HOST_V3'] = 'h5-api.aoneroom.com'
# ============================================

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Any, Dict
import asyncio
import logging
from datetime import datetime
import json

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
# MOVIEBOX IMPORT WITH FALLBACKS
# ============================================
MOVIEBOX_AVAILABLE = False
client_v2 = None
client_v3 = None

try:
    # Try importing from moviebox_api
    from moviebox_api.v2 import MovieAuto
    from moviebox_api.v3 import MovieAuto as MovieAutoV3
    
    client_v2 = MovieAuto()
    client_v3 = MovieAutoV3()
    MOVIEBOX_AVAILABLE = True
    logger.info("✅ MovieBox API loaded successfully")
    
except ImportError as e:
    logger.error(f"❌ MovieBox API import failed: {e}")
    
    # Try alternative import structure
    try:
        import moviebox_api
        logger.info(f"✅ Found moviebox_api module at: {moviebox_api.__file__}")
        
        # Try different import patterns
        try:
            from moviebox_api import v2
            from moviebox_api import v3
            client_v2 = v2.MovieAuto()
            client_v3 = v3.MovieAuto()
            MOVIEBOX_AVAILABLE = True
            logger.info("✅ MovieBox API loaded via alternative import")
        except:
            pass
    except ImportError:
        pass

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
            "v2": os.environ.get('MOVIEBOX_API_HOST_V2', 'h5-api.aoneroom.com'),
            "v3": os.environ.get('MOVIEBOX_API_HOST_V3', 'h5-api.aoneroom.com')
        },
        "endpoints": [
            {"path": "/", "method": "GET", "description": "API information"},
            {"path": "/health", "method": "GET", "description": "Health check"},
            {"path": "/search", "method": "GET", "description": "Search movies/series", "params": ["query", "version"]},
            {"path": "/movie", "method": "GET", "description": "Get movie details", "params": ["title", "quality", "language", "version"]},
            {"path": "/series", "method": "GET", "description": "Get TV series episode", "params": ["title", "season", "episode", "quality", "language", "version"]},
            {"path": "/home", "method": "GET", "description": "Homepage content", "params": ["version"]},
            {"path": "/mirrors", "method": "GET", "description": "Available mirrors", "params": ["version"]},
            {"path": "/suggest", "method": "GET", "description": "Search suggestions", "params": ["query", "version"]},
            {"path": "/cache-info", "method": "GET", "description": "Cache information"},
            {"path": "/clear-cache", "method": "POST", "description": "Clear cache"}
        ],
        "examples": {
            "search": "/search?query=avatar&version=v2",
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
        "mirrors": {
            "v2": os.environ.get('MOVIEBOX_API_HOST_V2', 'h5-api.aoneroom.com'),
            "v3": os.environ.get('MOVIEBOX_API_HOST_V3', 'h5-api.aoneroom.com')
        },
        "cache_size": len(cache)
    }

# ============================================
# SEARCH ENDPOINT
# ============================================

@app.get("/search", response_model=SearchResponse)
async def search(
    query: str = Query(..., description="Search term (e.g., avatar, game of thrones)"),
    version: str = Query("v2", description="API version: v2 or v3")
):
    """
    Search for movies and TV series
    
    Example: /search?query=avatar&version=v2
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
        
        # Get results based on version
        if version == "v3":
            results = await client_v3.search(query)
        else:
            results = await client_v2.search(query)
        
        # Normalize results to a list
        if isinstance(results, dict):
            if 'results' in results:
                results = results['results']
            elif 'data' in results:
                results = results['data']
            else:
                results = [results]
        elif not isinstance(results, list):
            results = [results] if results else []
        
        # Clean up results
        cleaned_results = []
        for item in results:
            if isinstance(item, dict):
                cleaned_item = {
                    'title': item.get('title', 'Unknown'),
                    'year': item.get('year', ''),
                    'type': item.get('type', 'movie'),
                    'slug': item.get('slug', item.get('id', '')),
                    'poster': item.get('poster', item.get('image', '')),
                    'rating': item.get('rating', '')
                }
                # Remove empty values
                cleaned_item = {k: v for k, v in cleaned_item.items() if v}
                cleaned_results.append(cleaned_item)
        
        response = SearchResponse(
            success=True,
            results=cleaned_results
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
# MOVIE DETAILS ENDPOINT
# ============================================

@app.get("/movie", response_model=MovieResponse)
async def get_movie(
    title: str = Query(..., description="Movie title"),
    quality: str = Query("best", description="Quality: best, 1080p, 720p, 480p, 360p, worst"),
    language: str = Query("English", description="Subtitle language"),
    version: str = Query("v2", description="API version: v2 or v3")
):
    """
    Get movie details and download URL
    
    Example: /movie?title=avatar&quality=1080p&version=v2
    """
    if not MOVIEBOX_AVAILABLE:
        return MovieResponse(
            success=False,
            error="MovieBox API not available. Please check installation."
        )
    
    cache_key = get_cache_key("movie", version, title.lower(), quality, language)
    cached = get_from_cache(cache_key)
    if cached:
        return cached
    
    try:
        logger.info(f"🎬 Fetching movie: {title} (quality: {quality}, version: {version})")
        
        # Choose client
        client = client_v3 if version == "v3" else client_v2
        
        # Get movie - try different method signatures
        try:
            movie_file, subtitle_file = await client.run(
                title, 
                quality=quality,
                language=language
            )
        except TypeError:
            # Fallback if method signature is different
            movie_file, subtitle_file = await client.run(title, quality=quality)
        
        # Extract data safely
        movie_data = {
            'title': getattr(movie_file, 'title', title),
            'quality': getattr(movie_file, 'quality', quality),
            'url': getattr(movie_file, 'url', None),
            'saved_to': str(getattr(movie_file, 'saved_to', '')) if hasattr(movie_file, 'saved_to') else None
        }
        
        subtitle_data = {
            'url': getattr(subtitle_file, 'url', None) if subtitle_file else None,
            'language': getattr(subtitle_file, 'language', language) if subtitle_file else None
        }
        
        response = MovieResponse(
            success=True,
            title=movie_data['title'],
            quality=movie_data['quality'],
            url=movie_data['url'],
            subtitle_url=subtitle_data['url']
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
# TV SERIES ENDPOINT
# ============================================

@app.get("/series", response_model=SeriesResponse)
async def get_series(
    title: str = Query(..., description="Series title"),
    season: int = Query(..., description="Season number", ge=1),
    episode: int = Query(..., description="Episode number", ge=1),
    quality: str = Query("best", description="Quality: best, 1080p, 720p, 480p, 360p, worst"),
    language: str = Query("English", description="Subtitle language"),
    limit: int = Query(1, description="Number of episodes to get", ge=1, le=50),
    version: str = Query("v2", description="API version: v2 or v3")
):
    """
    Get TV series episode details
    
    Example: /series?title=game%20of%20thrones&season=1&episode=1&version=v2
    """
    if not MOVIEBOX_AVAILABLE:
        return SeriesResponse(
            success=False,
            error="MovieBox API not available. Please check installation."
        )
    
    cache_key = get_cache_key("series", version, title.lower(), season, episode, quality, language, limit)
    cached = get_from_cache(cache_key)
    if cached:
        return cached
    
    try:
        logger.info(f"📺 Fetching series: {title} S{season}E{episode} (quality: {quality}, version: {version})")
        
        # Choose client
        client = client_v3 if version == "v3" else client_v2
        
        # Get series - try different method signatures
        try:
            result = await client.get_series(
                title,
                season,
                episode,
                quality=quality,
                language=language,
                limit=limit
            )
        except TypeError:
            try:
                result = await client.get_series(
                    title,
                    season,
                    episode,
                    quality=quality,
                    language=language
                )
            except:
                result = await client.get_series(title, season, episode, quality=quality)
        
        # Normalize result
        if isinstance(result, tuple):
            # If result is a tuple of (episode_file, subtitle_file)
            episode_data = {
                'episode': episode,
                'season': season,
                'title': title,
                'url': getattr(result[0], 'url', None) if result[0] else None,
                'quality': quality,
                'subtitle_url': getattr(result[1], 'url', None) if len(result) > 1 and result[1] else None
            }
            result = episode_data
        elif isinstance(result, dict):
            # Already a dict, just ensure required fields
            if 'episode' not in result:
                result['episode'] = episode
            if 'season' not in result:
                result['season'] = season
            if 'title' not in result:
                result['title'] = title
        
        response = SeriesResponse(
            success=True,
            data=result
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
    version: str = Query("v2", description="API version: v2 or v3")
):
    """
    Get homepage content (banners, trending, popular, etc.)
    
    Example: /home?version=v2
    """
    if not MOVIEBOX_AVAILABLE:
        return {"success": False, "error": "MovieBox API not available"}
    
    cache_key = get_cache_key("homepage", version)
    cached = get_from_cache(cache_key)
    if cached:
        return cached
    
    try:
        logger.info(f"🏠 Fetching homepage content using version {version}")
        
        # Choose client
        client = client_v3 if version == "v3" else client_v2
        
        # Get homepage content - try different methods
        try:
            content = await client.get_homepage()
        except AttributeError:
            # Fallback: try get_home or get_index
            try:
                content = await client.get_home()
            except:
                content = await client.get_index()
        
        # Normalize content
        if isinstance(content, dict):
            # Ensure we have the expected structure
            if 'banners' not in content:
                content['banners'] = []
            if 'trending' not in content:
                content['trending'] = []
            if 'popular' not in content:
                content['popular'] = []
        
        response = {
            "success": True,
            "version": version,
            "content": content
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
async def get_mirrors(
    version: str = Query("v2", description="API version: v2 or v3")
):
    """
    Get available mirror hosts
    
    Example: /mirrors?version=v2
    """
    if not MOVIEBOX_AVAILABLE:
        return {"success": False, "error": "MovieBox API not available"}
    
    try:
        logger.info(f"🪞 Fetching mirrors for version {version}")
        
        # Choose client
        client = client_v3 if version == "v3" else client_v2
        
        # Get mirrors - try different methods
        try:
            mirrors = await client.get_mirrors()
        except AttributeError:
            mirrors = ["h5-api.aoneroom.com", "h5.aoneroom.com"]
        
        return {
            "success": True,
            "version": version,
            "current_mirror": os.environ.get(f'MOVIEBOX_API_HOST_{version.upper()}', 'h5-api.aoneroom.com'),
            "mirrors": mirrors
        }
        
    except Exception as e:
        logger.error(f"❌ Mirrors fetch error: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to fetch mirrors: {str(e)}"
        }

# ============================================
# SEARCH SUGGESTIONS ENDPOINT
# ============================================

@app.get("/suggest")
async def get_suggestions(
    query: str = Query(..., description="Search term for suggestions"),
    version: str = Query("v2", description="API version: v2 or v3")
):
    """
    Get search suggestions/autocomplete
    
    Example: /suggest?query=ava&version=v2
    """
    if not MOVIEBOX_AVAILABLE:
        return {"success": False, "error": "MovieBox API not available"}
    
    cache_key = get_cache_key("suggest", version, query.lower())
    cached = get_from_cache(cache_key)
    if cached:
        return cached
    
    try:
        logger.info(f"💡 Getting suggestions for: {query} using version {version}")
        
        # Choose client
        client = client_v3 if version == "v3" else client_v2
        
        # Get suggestions - try different methods
        suggestions = []
        try:
            if hasattr(client, 'get_suggestions'):
                suggestions = await client.get_suggestions(query)
            else:
                # Fallback: use search and extract titles
                results = await client.search(query)
                if isinstance(results, dict) and 'results' in results:
                    suggestions = [item.get('title') for item in results['results'][:5]]
                elif isinstance(results, list):
                    suggestions = [item.get('title') for item in results[:5]]
                else:
                    suggestions = []
        except:
            suggestions = []
        
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
        "max_duration_seconds": CACHE_DURATION,
        "keys_by_endpoint": {
            "search": [k for k in cache.keys() if k.startswith("search_")],
            "movie": [k for k in cache.keys() if k.startswith("movie_")],
            "series": [k for k in cache.keys() if k.startswith("series_")],
            "homepage": [k for k in cache.keys() if k.startswith("homepage_")],
            "suggest": [k for k in cache.keys() if k.startswith("suggest_")]
        }
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

