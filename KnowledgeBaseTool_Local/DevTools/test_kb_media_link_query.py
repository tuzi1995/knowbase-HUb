import server


class LinksResponse:
    status_code = 200
    headers = {'Content-Range': '0-1/2'}

    def json(self):
        return [
            {'id': 'image-1', 'kb_id': None, 'url': 'https://example.com/a.png', 'type': 'image', 'tags': ['manual'], 'created_at': '2026-01-01'},
            {'id': 'video-1', 'kb_id': None, 'url': 'https://example.com/a.mp4', 'type': 'video', 'tags': ['manual'], 'created_at': '2026-01-02'},
        ]


class LinksClient:
    def __init__(self):
        self.filters = None

    def select(self, table, **kwargs):
        assert table == 'link_previews'
        self.filters = kwargs['filters']
        return LinksResponse()


def test_media_query_keeps_type_and_tag_filters(monkeypatch):
    client = LinksClient()
    monkeypatch.setattr(server, 'get_supabase_client', lambda: client)
    monkeypatch.setitem(server.app.config, 'LOGIN_DISABLED', True)

    response = server.app.test_client().get('/api/links?linkType=media&tags=manual&page=1&pageSize=30')

    assert response.status_code == 200
    assert [row['type'] for row in response.json['data']] == ['image', 'video']
    assert client.filters['type'] == 'in.(image,video)'
    assert client.filters['or'] == '(tags.cs.["manual"])'


def test_image_and_video_queries_filter_exact_media_type(monkeypatch):
    for link_type in ('image', 'video'):
        client = LinksClient()
        monkeypatch.setattr(server, 'get_supabase_client', lambda client=client: client)
        monkeypatch.setitem(server.app.config, 'LOGIN_DISABLED', True)

        response = server.app.test_client().get(
            f'/api/links?linkType={link_type}&page=1&pageSize=30'
        )

        assert response.status_code == 200
        assert client.filters['type'] == f'eq.{link_type}'
