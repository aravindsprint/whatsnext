from whatsnext.whatsnext.api import is_meta_hosted_url, meta_header_sample_url

META_URL = "https://scontent.whatsapp.net/v/t61.29466-34/x.jpg?oe=6B05087A"


def test_meta_hosted_urls_are_refreshable():
	assert is_meta_hosted_url(META_URL)
	assert is_meta_hosted_url("https://scontent-bom1-1.xx.fbcdn.net/v/a.png")
	assert is_meta_hosted_url("")
	assert is_meta_hosted_url(None)


def test_own_links_are_kept():
	assert not is_meta_hosted_url("https://erp.pranera.in/files/mars200.jpg")
	assert not is_meta_hosted_url("https://cdn.example.com/whatsapp.net.jpg")


def test_header_sample_url_from_meta_template():
	t = {"components": [
		{"type": "HEADER", "format": "IMAGE", "example": {"header_handle": [META_URL]}},
		{"type": "BODY", "text": "Hi"},
	]}
	assert meta_header_sample_url(t) == META_URL
	assert meta_header_sample_url({"components": [{"type": "HEADER", "format": "TEXT", "text": "Hello"}]}) == ""
	assert meta_header_sample_url({}) == ""
