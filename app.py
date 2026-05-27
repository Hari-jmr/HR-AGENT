import logging
import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('openai').setLevel(logging.WARNING)

from backend.main import app


if __name__ == '__main__':
    uvicorn.run('backend.main:app', host='0.0.0.0', port=5000, reload=False)
