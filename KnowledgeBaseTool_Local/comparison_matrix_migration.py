"""Idempotent local ledger migration for product comparison images."""
def upgrade(db, models):
    """Create additive comparison tables without touching existing data."""
    with db.engine.begin() as connection:
        for model in models:
            model.__table__.create(connection, checkfirst=True)
    return [model.__tablename__ for model in models]


if __name__ == '__main__':
    import argparse
    import os
    parser = argparse.ArgumentParser(description='只为指定平台 SQLite 创建产品对比台账表，不修改 KB')
    parser.add_argument('--sqlite-path', required=True, help='平台运行时 SQLite 的绝对路径')
    args = parser.parse_args()
    if not os.path.isabs(args.sqlite_path):
        parser.error('--sqlite-path 必须是绝对路径')
    os.environ['KMATRIX_SQLITE_PATH'] = args.sqlite_path
    import server
    with server.app.app_context():
        print('已创建或检查：', ', '.join(upgrade(server.db, server.COMPARISON_MODELS)))
