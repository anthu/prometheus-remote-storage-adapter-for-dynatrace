"""Flask configuration."""
from os import environ, path
from dotenv import load_dotenv

basedir = path.abspath(path.dirname(__file__))
load_dotenv(path.join(basedir, '.env'))

DT_TENANT = environ.get('DT_TENANT')
DT_API_TOKEN = environ.get('DT_API_TOKEN')


if not DT_TENANT:
    raise ValueError("No DT_TENANT set for Flask application")


if not DT_API_TOKEN:
    raise ValueError("No DT_API_TOKEN set for Flask application")
