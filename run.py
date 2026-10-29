"""Start the Coupang Scraper API.

    python run.py                                              # http://localhost:8000
    COUPANG_PROXY=http://user:pass@host:port python run.py     # through a Korean residential proxy
    PORT=9000 python run.py                                    # another port

Then:  curl "http://localhost:8000/products/best?category=electronics"
"""
import bottle
from cheroot import wsgi

import config
import routes  # noqa: F401  (mounts the routes on bottle's default app)


def main():
    app = bottle.default_app()
    print(f"Coupang Scraper listening on http://localhost:{config.PORT}/")
    if not config.COUPANG_PROXY:
        print("NOTE: COUPANG_PROXY is not set. The open feeds work from most connections; product search, "
              "product details / reviews / questions, category pages and seller catalogues need a sticky "
              "residential proxy in South Korea.")
    print(f"Try:  curl \"http://localhost:{config.PORT}/products/best?category=electronics\"")
    server = wsgi.Server(("0.0.0.0", config.PORT), app, server_name="coupang-scraper", numthreads=16)
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    main()
