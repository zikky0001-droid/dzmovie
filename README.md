# DZMovie API

🚀 A REST API wrapper for MovieBox.ph built with FastAPI and the official moviebox-api library.

## ✨ Features

- 🔍 **Search** movies and TV series
- 📥 **Get movie** download URLs with quality selection
- 📺 **Get TV series** episodes
- 🏠 **Homepage content** (trending, banners, popular)
- 💡 **Search suggestions** autocomplete
- 🔄 **Multi-version support** (v2 and v3)
- 🪞 **Mirror host** discovery
- ⚡ **Caching** for better performance
- 🎯 **Free tier** optimized

## 🚀 Quick Start

### Deploy on Render

1. Fork this repository
2. Go to [Render.com](https://render.com)
3. Click **New+** → **Web Service**
4. Connect your GitHub repository
5. Use these settings:
   - **Environment**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn api:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: Free

### Local Development

```bash
# Clone the repository
git clone https://github.com/yourusername/dzmovie.git
cd dzmovie

# Install dependencies
pip install -r requirements.txt

# Run the API
uvicorn api:app --reload
