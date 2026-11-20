import sqlite3
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from agente_ia.sql_manager import ConnectionConfig, SqlManager, backup_sqlite, connection_url, safe_error, validate_statement


@pytest.fixture
def database(tmp_path):
    path = tmp_path/'catálogo.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE products(id INTEGER PRIMARY KEY, name TEXT, price REAL)')
        db.execute("INSERT INTO products(name,price) VALUES('Agua',10)")
    return path


def test_catalog_query_update_and_verified_backup(database, tmp_path):
    manager = SqlManager(ConnectionConfig('SQLite', database=str(database)))
    assert manager.perform('catalog')['tables'] == ['products']
    assert manager.perform('columns', table='products')['columns'][1][0] == 'name'
    assert manager.perform('query', sql='SELECT name FROM products')['rows'] == [['Agua']]
    with pytest.raises(ValueError):
        manager.perform('query', sql='UPDATE products SET price=99')
    manager.perform('query', sql='UPDATE products SET price=12', allow_changes=True)
    backup = tmp_path/'copy.db'
    backup_sqlite(database, backup)
    with sqlite3.connect(backup) as db:
        assert db.execute('SELECT price FROM products').fetchone()[0] == 12
    with pytest.raises(ValueError): backup_sqlite(database, database)
    with pytest.raises(ValueError): backup_sqlite(database, backup)


def test_sqlite_readonly_is_enforced_by_engine(database):
    url, args = connection_url(ConnectionConfig('SQLite', database=str(database)))
    engine = create_engine(url, connect_args=args)
    try:
        with engine.connect() as connection:
            with pytest.raises(Exception, match='readonly'):
                connection.exec_driver_sql('DELETE FROM products')
    finally:
        engine.dispose()


@pytest.mark.parametrize('sql', ['SELECT 1; DELETE FROM products', 'SELECT * INTO other FROM products', 'WITH x AS (DELETE FROM products RETURNING *) SELECT * FROM x', 'CALL cleanup()', 'PRAGMA query_only=OFF'])
def test_consultation_guard_rejects_writes(sql):
    with pytest.raises(ValueError): validate_statement(sql)


def test_bounded_results_and_failed_write_rolls_back(database):
    with sqlite3.connect(database) as db:
        db.executemany('INSERT INTO products(name,price) VALUES(?,?)', [('x',1)]*600)
    manager = SqlManager(ConnectionConfig('SQLite', database=str(database)))
    result = manager.perform('query', sql='SELECT * FROM products')
    assert len(result['rows']) == 500 and result['truncated']
    with pytest.raises(Exception): manager.perform('query', sql='INSERT INTO missing VALUES(1)', allow_changes=True)
    assert manager.perform('query', sql='SELECT count(*) FROM products')['rows'] == [['601']]


def test_connection_urls_quote_credentials_and_tls():
    for motor in ['SQL Server','PostgreSQL','MySQL','MariaDB','Oracle']:
        config = ConnectionConfig(motor, database='example', user='user', password='a@b:/#')
        url, args = connection_url(config)
        assert url.password == config.password
        assert config.password not in str(url)
        assert 'a@b:/#' not in safe_error(Exception('failed a@b:/#'), config)
    config = ConnectionConfig('SQL Server', database='example')
    url, _ = connection_url(config)
    assert url.query['Encrypt'] == 'yes' and url.query['TrustServerCertificate'] == 'no'


def test_missing_sqlite_does_not_create_file(tmp_path):
    path = tmp_path/'missing.db'
    with pytest.raises(ValueError): connection_url(ConnectionConfig('SQLite', database=str(path)))
    assert not path.exists()


def test_backup_releases_file_handles(database, tmp_path):
    backup = tmp_path/'released.db'
    backup_sqlite(database, backup)
    renamed = tmp_path/'renamed.db'
    backup.rename(renamed)
    renamed.unlink()
    assert not renamed.exists()
