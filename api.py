# ============================================
# MOVIEBOX API - V1 PRIMARY WITH V3 FALLBACK
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

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(
    title="DZMovie API",
    description="MovieBox API - V1 with V3 fallback",
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
# MOVIEBOX V1 & V3 IMPORTS
# ============================================
V1_AVAILABLE = False
V3_AVAILABLE = False

# Try V1
try:
    from moviebox_api.v1 import (
        MovieAuto as MovieAutoV1,
        Search as SearchV1,
        Session as SessionV1,
        SubjectType as SubjectTypeV1,
        MovieDetails as MovieDetailsV1,
        TVSeriesDetails as TVSeriesDetailsV1,
        DownloadableMovieFilesDetail as DownloadableMovieFilesDetailV1,
        DownloadableTVSeriesFilesDetail as DownloadableTVSeriesFilesDetailV1,
    )
    from moviebox_api.v1.download import MediaFileDownloader, CaptionFileDownloader
    V1_AVAILABLE = True
    logger.info("✅ MovieBox V1 loaded successfully")
except ImportError as e:
    logger.warning(f"⚠️ V1 import failed: {e}")

# Try V3
try:
    from moviebox_api.v3 import (
        MovieAuto as MovieAutoV3,
        Search as SearchV3,
        Session as SessionV3,
        SubjectType as SubjectTypeV3,
        MovieDetails as MovieDetailsV3,
        TVSeriesDetails as TVSeriesDetailsV3,
        DownloadableMovieFilesDetail as DownloadableMovieFilesDetailV3,
        DownloadableTVSeriesFilesDetail as DownloadableTVSeriesFilesDetailV3,
    )
    V3_AVAILABLE = True
    logger.info("✅ MovieBox V3 loaded successfully")
except ImportError as e:
    logger.warning(f"⚠️ V3 import failed: {e}")

MOVIEBOX_AVAILABLE = V1_AVAILABLE or V3_AVAILABLE

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
# HELPER FUNCTIONS
# ============================================

def get_subject_type_v1(subject_type: str):
    """Map subject type for V1"""
    type_map = {
        "movies": SubjectTypeV1.MOVIES,
        "tv_series": SubjectTypeV1.TV_SERIES,
        "anime": SubjectTypeV1.ANIME,
        "music": SubjectTypeV1.MUSIC,
        "education": SubjectTypeV1.EDUCATION,
    }
    return type_map.get(subject_type, SubjectTypeV1.MOVIES)

def get_subject_type_v3(subject_type: str):
    """Map subject type for V3"""
    type_map = {
        "movies": SubjectTypeV3.MOVIES,
        "tv_series": SubjectTypeV3.TV_SERIES,
        "anime": SubjectTypeV3.ANIME,
        "music": SubjectTypeV3.MUSIC,
        "education": SubjectTypeV3.EDUCATION,
    }
    return type_map.get(subject_type, SubjectTypeV3.MOVIES)

# ============================================
# ROOT ENDPOINT
# ============================================

@app.get("/")
async def root():
    return {
        "name": "DZMovie API",
        "version": "1.0.0",
        "status": "running" if MOVIEBOX_AVAILABLE else "degraded",
        "versions": {
            "v1": V1_AVAILABLE,
            "v3": V3_AVAILABLE
        },
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
        "versions": {
            "v1": V1_AVAILABLE,
            "v3": V3_AVAILABLE
        },
        "cache_size": len(cache)
    }

# ============================================
# SEARCH ENDPOINT - V1 with V3 fallback
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
    
    # Try V1 first
    if V1_AVAILABLE:
        try:
            logger.info(f"🔍 V1 Search: {query} ({subject_type})")
            
            session = SessionV1()
            search_obj = SearchV1(
                session=session,
                query=query,
                subject_type=get_subject_type_v1(subject_type)
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
            logger.warning(f"⚠️ V1 search failed: {e}, trying V3...")
    
    # Fallback to V3
    if V3_AVAILABLE:
        try:
            logger.info(f"🔍 V3 Search: {query} ({subject_type})")
            
            session = SessionV3()
            search_obj = SearchV3(
                session=session,
                query=query,
                subject_type=get_subject_type_v3(subject_type)
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
            
            response = SearchResponse(success=True, results=results, version_used="v3")
            set_cache(cache_key, response)
            return response
            
        except Exception as e:
            logger.error(f"❌ V3 search also failed: {e}")
    
    return SearchResponse(success=False, error="All versions failed")

# ============================================
# MOVIE ENDPOINT - V1 with V3 fallback
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
    
    # Try V1 first
    if V1_AVAILABLE:
        try:
            logger.info(f"🎬 V1 Movie: {title} ({quality})")
            
            session = SessionV1()
            
            # Search for the movie
            search_obj = SearchV1(
                session=session,
                query=title,
                subject_type=SubjectTypeV1.MOVIES
            )
            search_results = await search_obj.get_content_model()
            
            if not search_results or not search_results.items:
                return MovieResponse(success=False, error=f"No results found for '{title}'")
            
            target_movie = search_results.items[0]
            
            # Get movie details
            movie_details = MovieDetailsV1(target_movie, session)
            details = await movie_details.get_content_model()
            
            # Get downloadable files
            downloadable = DownloadableMovieFilesDetailV1(session, details)
            files_detail = await downloadable.get_content_model()
            
            # Get best quality file
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
                subtitle_url=subtitle_url,
                version_used="v1"
            )
            
            set_cache(cache_key, response)
            return response
            
        except Exception as e:
            logger.warning(f"⚠️ V1 movie failed: {e}, trying V3...")
    
    # Fallback to V3
    if V3_AVAILABLE:
        try:
            logger.info(f"🎬 V3 Movie: {title} ({quality})")
            
            session = SessionV3()
            
            # Search for the movie
            search_obj = SearchV3(
                session=session,
                query=title,
                subject_type=SubjectTypeV3.MOVIES
            )
            search_results = await search_obj.get_content_model()
            
            if not search_results or not search_results.items:
                return MovieResponse(success=False, error=f"No results found for '{title}'")
            
            target_movie = search_results.items[0]
            
            # Get movie details
            movie_details = MovieDetailsV3(target_movie, session)
            details = await movie_details.get_content_model()
            
            # Get downloadable files
            downloadable = DownloadableMovieFilesDetailV3(session, details)
            files_detail = await downloadable.get_content_model()
            
            # Get best quality file
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
                subtitle_url=subtitle_url,
                version_used="v3"
            )
            
            set_cache(cache_key, response)
            return response
            
        except Exception as e:
            logger.error(f"❌ V3 movie also failed: {e}")
    
    return MovieResponse(success=False, error="All versions failed")

# ============================================
# SERIES ENDPOINT - V1 with V3 fallback
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
    
    # Try V1 first
    if V1_AVAILABLE:
        try:
            logger.info(f"📺 V1 Series: {title} S{season}E{episode}")
            
            session = SessionV1()
            
            # Search for the series
            search_obj = SearchV1(
                session=session,
                query=title,
                subject_type=SubjectTypeV1.TV_SERIES
            )
            search_results = await search_obj.get_content_model()
            
            if not search_results or not search_results.items:
                return {"success": False, "error": f"No results found for '{title}'"}
            
            target_series = search_results.items[0]
            
            # Get series details
            series_details = TVSeriesDetailsV1(target_series, session)
            details = await series_details.get_content_model()
            
            # Get downloadable files for specific episode
            downloadable = DownloadableTVSeriesFilesDetailV1(session, details)
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
                "version_used": "v1",
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
            logger.warning(f"⚠️ V1 series failed: {e}, trying V3...")
    
    # Fallback to V3
    if V3_AVAILABLE:
        try:
            logger.info(f"📺 V3 Series: {title} S{season}E{episode}")
            
            session = SessionV3()
            
            # Search for the series
            search_obj = SearchV3(
                session=session,
                query=title,
                subject_type=SubjectTypeV3.TV_SERIES
            )
            search_results = await search_obj.get_content_model()
            
            if not search_results or not search_results.items:
                return {"success": False, "error": f"No results found for '{title}'"}
            
            target_series = search_results.items[0]
            
            # Get series details
            series_details = TVSeriesDetailsV3(target_series, session)
            details = await series_details.get_content_model()
            
            # Get downloadable files for specific episode
            downloadable = DownloadableTVSeriesFilesDetailV3(session, details)
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
                "version_used": "v3",
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
            logger.error(f"❌ V3 series also failed: {e}")
    
    return {"success": False, "error": "All versions failed"}

# ============================================
# HOMEPAGE ENDPOINT - V1 with V3 fallback
# ============================================

@app.get("/home")
async def get_homepage():
    if not MOVIEBOX_AVAILABLE:
        return {"success": False, "error": "MovieBox API not available"}
    
    cache_key = "homepage"
    cached = get_from_cache(cache_key)
    if cached:
        return cached
    
    # Try V1 first
    if V1_AVAILABLE:
        try:
            logger.info("🏠 V1 Homepage")
            
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
            logger.warning("⚠️ V1 HomepageContent not available, trying V3...")
        except Exception as e:
            logger.warning(f"⚠️ V1 homepage failed: {e}, trying V3...")
    
    # Fallback to V3
    if V3_AVAILABLE:
        try:
            logger.info("🏠 V3 Homepage")
            
            from moviebox_api.v3 import HomepageContent
            
            homepage = HomepageContent()
            content = await homepage.get_content_model()
            
            result = {
                "success": True,
                "version_used": "v3",
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
            logger.error(f"❌ V3 homepage failed: {e}")
    
    return {"success": False, "error": "All versions failed"}

# ============================================
# MIRRORS ENDPOINT
# ============================================

@app.get("/mirrors")
async def get_mirrors():
    mirrors = ["h5.aoneroom.com", "h5-api.aoneroom.com"]
    
    # Try to get from V1
    if V1_AVAILABLE:
        try:
            from moviebox_api.v1 import MirrorHosts
            mirror_hosts = MirrorHosts()
            results = await mirror_hosts.get_content()
            if results:
                mirrors = results if isinstance(results, list) else [results]
        except Exception as e:
            logger.warning(f"⚠️ V1 mirrors failed: {e}")
    
    return {
        "success": True,
        "mirrors": mirrors,
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

