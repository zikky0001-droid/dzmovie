# ============================================
# MOVIEBOX MIRROR HOSTS CONFIGURATION
# ============================================
import os
os.environ['MOVIEBOX_API_HOST_V2'] = 'h5-api.aoneroom.com'
os.environ['MOVIEBOX_API_HOST_V3'] = 'h5-api.aoneroom.com'
# ============================================

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, StreamingResponse
from moviebox_api.v2 import MovieAuto
from moviebox_api.v3 import MovieAuto as MovieAutoV3
from pydantic import BaseModel
from typing import Optional, List
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

# Initialize clients with mirror hosts already set
client_v2 = MovieAuto()
client_v3 = MovieAutoV3()

# Cache for better performance
cache = {}
CACHE_DURATION = 300  # 5 minutes

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
    results: Optional[List[dict]] = None
    error: Optional[str] = None

class SeriesResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None

# ============================================
# ROOT ENDPOINT
# ============================================

@app.get("/")
async def root():
    """Welcome endpoint"""
    return {
        "name": "DZMovie API",
        "version": "1.0.0",
        "status": "running",
        "mirrors": {
            "v2": os.environ.get('MOVIEBOX_API_HOST_V2'),
            "v3": os.environ.get('MOVIEBOX_API_HOST_V3')
        },
        "endpoints": [
            "/search?query=avatar&version=v2",
            "/movie?title=avatar&quality=1080p&version=v2",
            "/series?title=game%20of%20thrones&season=1&episode=1&version=v2",
            "/home?version=v2",
            "/mirrors?version=v2",
            "/health"
        ]
    }

# ============================================
# HEALTH CHECK
# ============================================

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "mirrors": {
            "v2": os.environ.get('MOVIEBOX_API_HOST_V2'),
            "v3": os.environ.get('MOVIEBOX_API_HOST_V3')
        }
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
    cache_key = f"search_{version}_{query.lower()}"
    
    # Check cache
    if cache_key in cache:
        cached_data, timestamp = cache[cache_key]
        if (datetime.now() - timestamp).seconds < CACHE_DURATION:
            logger.info(f"Returning cached search result for: {query}")
            return cached_data
    
    try:
        logger.info(f"Searching for: {query} using version {version}")
        
        if version == "v3":
            results = await client_v3.search(query)
        else:
            results = await client_v2.search(query)
        
        # Ensure results is a list
        if isinstance(results, dict) and 'results' in results:
            results = results['results']
        elif not isinstance(results, list):
            results = [results] if results else []
        
        response = SearchResponse(
            success=True,
            results=results
        )
        
        # Cache the response
        cache[cache_key] = (response, datetime.now())
        
        return response
        
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
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
    year: Optional[int] = Query(None, description="Release year filter"),
    language: str = Query("English", description="Subtitle language"),
    version: str = Query("v2", description="API version: v2 or v3")
):
    """
    Get movie details and download URL
    
    Example: /movie?title=avatar&quality=1080p&version=v2
    """
    cache_key = f"movie_{version}_{title.lower()}_{quality}_{year}_{language}"
    
    # Check cache
    if cache_key in cache:
        cached_data, timestamp = cache[cache_key]
        if (datetime.now() - timestamp).seconds < CACHE_DURATION:
            logger.info(f"Returning cached movie data for: {title}")
            return cached_data
    
    try:
        logger.info(f"Fetching movie: {title} (quality: {quality}, version: {version})")
        
        # Choose client
        client = client_v3 if version == "v3" else client_v2
        
        # Get movie
        if version == "v3":
            movie_file, subtitle_file = await client.run(
                title, 
                quality=quality,
                language=language
            )
        else:
            movie_file, subtitle_file = await client.run(
                title,
                quality=quality,
                language=language
            )
        
        response = MovieResponse(
            success=True,
            title=getattr(movie_file, 'title', title),
            quality=getattr(movie_file, 'quality', quality),
            url=getattr(movie_file, 'url', None),
            subtitle_url=getattr(subtitle_file, 'url', None) if subtitle_file else None
        )
        
        # Cache the response
        cache[cache_key] = (response, datetime.now())
        
        return response
        
    except Exception as e:
        logger.error(f"Movie fetch error: {str(e)}")
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
    limit: int = Query(1, description="Number of episodes to get", ge=1),
    version: str = Query("v2", description="API version: v2 or v3")
):
    """
    Get TV series episode details
    
    Example: /series?title=game%20of%20thrones&season=1&episode=1&version=v2
    """
    cache_key = f"series_{version}_{title.lower()}_s{season}_e{episode}_{quality}_{language}"
    
    # Check cache
    if cache_key in cache:
        cached_data, timestamp = cache[cache_key]
        if (datetime.now() - timestamp).seconds < CACHE_DURATION:
            logger.info(f"Returning cached series data for: {title} S{season}E{episode}")
            return cached_data
    
    try:
        logger.info(f"Fetching series: {title} S{season}E{episode} (quality: {quality}, version: {version})")
        
        # Choose client
        client = client_v3 if version == "v3" else client_v2
        
        # Get series
        if version == "v3":
            result = await client.get_series(
                title,
                season,
                episode,
                quality=quality,
                language=language,
                limit=limit
            )
        else:
            result = await client.get_series(
                title,
                season,
                episode,
                quality=quality,
                language=language,
                limit=limit
            )
        
        response = SeriesResponse(
            success=True,
            data=result
        )
        
        # Cache the response
        cache[cache_key] = (response, datetime.now())
        
        return response
        
    except Exception as e:
        logger.error(f"Series fetch error: {str(e)}")
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
    cache_key = f"homepage_{version}"
    
    # Check cache
    if cache_key in cache:
        cached_data, timestamp = cache[cache_key]
        if (datetime.now() - timestamp).seconds < CACHE_DURATION:
            logger.info(f"Returning cached homepage data")
            return cached_data
    
    try:
        logger.info(f"Fetching homepage content using version {version}")
        
        # Choose client
        client = client_v3 if version == "v3" else client_v2
        
        # Get homepage content
        if version == "v3":
            content = await client.get_homepage()
        else:
            content = await client.get_homepage()
        
        response = {
            "success": True,
            "version": version,
            "content": content
        }
        
        # Cache the response
        cache[cache_key] = (response, datetime.now())
        
        return response
        
    except Exception as e:
        logger.error(f"Homepage fetch error: {str(e)}")
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
    try:
        logger.info(f"Fetching mirrors for version {version}")
        
        # Choose client
        client = client_v3 if version == "v3" else client_v2
        
        # Get mirrors
        mirrors = await client.get_mirrors()
        
        return {
            "success": True,
            "version": version,
            "current_mirror": os.environ.get(f'MOVIEBOX_API_HOST_{version.upper()}'),
            "mirrors": mirrors
        }
        
    except Exception as e:
        logger.error(f"Mirrors fetch error: {str(e)}")
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
    cache_key = f"suggest_{version}_{query.lower()}"
    
    # Check cache
    if cache_key in cache:
        cached_data, timestamp = cache[cache_key]
        if (datetime.now() - timestamp).seconds < CACHE_DURATION:
            return cached_data
    
    try:
        logger.info(f"Getting suggestions for: {query} using version {version}")
        
        # Choose client
        client = client_v3 if version == "v3" else client_v2
        
        # Get suggestions
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
        
        response = {
            "success": True,
            "query": query,
            "suggestions": suggestions
        }
        
        cache[cache_key] = (response, datetime.now())
        return response
        
    except Exception as e:
        logger.error(f"Suggestions error: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to get suggestions: {str(e)}"
        }

# ============================================
# CLEAR CACHE ENDPOINT (Admin)
# ============================================

@app.post("/clear-cache")
async def clear_cache():
    """Clear the API cache"""
    global cache
    cache.clear()
    return {"success": True, "message": "Cache cleared"}

# ============================================
# CACHE INFO ENDPOINT
# ============================================

@app.get("/cache-info")
async def cache_info():
    """Get cache information"""
    return {
        "cache_size": len(cache),
        "cache_keys": list(cache.keys()),
        "max_duration_seconds": CACHE_DURATION
    }

# ============================================
# RUN THE APP
# ============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )

