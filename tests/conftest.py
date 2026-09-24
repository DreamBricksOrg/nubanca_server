import boto3
import pytest
from moto import mock_aws

from app import create_app
from app.config import Config

TEST_S3_BUCKET = "test-bucket"


@pytest.fixture
def app(tmp_path):
    class TestConfig(Config):
        STORAGE_ROOT = tmp_path
        BASE_URL = "http://testserver"
        AWS_ACCESS_KEY_ID = "testing"
        AWS_SECRET_ACCESS_KEY = "testing"
        AWS_REGION = "us-east-1"
        AWS_S3_BUCKET = TEST_S3_BUCKET
        S3_PRESIGNED_URL_EXPIRES = 3600

    with mock_aws():
        s3 = boto3.client("s3", region_name=TestConfig.AWS_REGION)
        s3.create_bucket(Bucket=TEST_S3_BUCKET)

        application = create_app(TestConfig)
        application.config["TESTING"] = True
        yield application


@pytest.fixture
def client(app):
    return app.test_client()
