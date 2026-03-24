from app.config import get_settings
from app.s3_client import get_s3_client


class FakeS3Client:
    def __init__(self):
        self.storage = {}

    def put_object(self, Bucket, Key, Body, ContentType):
        self.storage[(Bucket, Key)] = {"Body": Body, "ContentType": ContentType}

    def generate_presigned_url(self, method, Params, ExpiresIn):
        return f"https://example.local/{Params['Bucket']}/{Params['Key']}?exp={ExpiresIn}"

    def delete_object(self, Bucket, Key):
        self.storage.pop((Bucket, Key), None)

    def get_object(self, Bucket, Key):
        body = self.storage[(Bucket, Key)]["Body"]
        return {"Body": _Reader(body)}


class _Reader:
    def __init__(self, value: bytes):
        self.value = value

    def read(self):
        return self.value


def test_s3_client_with_mock(monkeypatch):
    fake_client = FakeS3Client()

    monkeypatch.setenv("S3_ENDPOINT", "https://s3.local")
    monkeypatch.setenv("S3_ACCESS_KEY", "key")
    monkeypatch.setenv("S3_SECRET_KEY", "secret")
    monkeypatch.setenv("S3_BUCKET", "bucket")

    get_settings.cache_clear()
    get_s3_client.cache_clear()

    import app.s3_client as s3_module

    monkeypatch.setattr(s3_module.boto3, "client", lambda *args, **kwargs: fake_client)

    s3 = get_s3_client()

    key = s3.upload_file(b"zip-data", "packs/1/pack.zip", "application/zip")
    assert key == "packs/1/pack.zip"

    url = s3.generate_download_url(key, expires_in=120)
    assert "exp=120" in url

    data = s3.download_file(key)
    assert data == b"zip-data"

    s3.delete_file(key)
    assert ("bucket", key) not in fake_client.storage
