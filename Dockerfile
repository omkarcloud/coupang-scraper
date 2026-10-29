FROM chetan1111/botasaurus:chrome-151

ENV PYTHONUNBUFFERED=1
# Never open debug prompts/devtools on crash.
ENV ENV=production

COPY requirements.txt .

RUN python -m pip install --no-cache-dir -r requirements.txt

RUN mkdir app
WORKDIR /app
COPY . /app

EXPOSE 8000

# The image ships real Google Chrome + Xvfb. Chrome serves the Coupang pages
# Akamai walls (search, category, product pages) and earns the store cookies
# the seller endpoints replay; the open feeds run over plain HTTP.
CMD ["python", "run.py"]
