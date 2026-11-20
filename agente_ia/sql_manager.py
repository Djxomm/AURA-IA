"""Bounded SQL operations. Credentials remain in memory, never in chat/history."""
from dataclasses import dataclass, field
from contextlib import closing
from pathlib import Path
import re
import os
import sqlite3
import ssl
import time

import sqlparse
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

MOTORS = ['SQLite', 'SQL Server', 'PostgreSQL', 'MySQL', 'MariaDB', 'Oracle', 'ODBC / DSN']
PORTS = {'SQL Server': 1433, 'PostgreSQL': 5432, 'MySQL': 3306, 'MariaDB': 3306, 'Oracle': 1521}
LIMIT = 500


@dataclass(frozen=True)
class ConnectionConfig:
    motor: str
    host: str = 'localhost'
    port: int = 0
    database: str = ''
    user: str = ''
    password: str = field(default='', repr=False)
    driver: str = 'ODBC Driver 18 for SQL Server'
    tls: bool = True


def validate_statement(sql, allow_changes=False):
    if len(sql) > 12000:
        raise ValueError('Divide el SQL en instrucciones de hasta 12000 caracteres para revisarlo completo.')
    statements = [part for part in sqlparse.split(sql.strip()) if part.strip()]
    if len(statements) != 1:
        raise ValueError('Ejecuta una sola instrucción por vez.')
    if not allow_changes:
        statement = sqlparse.parse(statements[0])[0]
        forbidden = {'INTO', 'INSERT', 'UPDATE', 'DELETE', 'MERGE', 'REPLACE', 'CREATE', 'ALTER', 'DROP', 'TRUNCATE', 'EXEC', 'EXECUTE', 'CALL', 'GRANT', 'REVOKE', 'ATTACH', 'DETACH', 'PRAGMA', 'VACUUM'}
        keywords = {token.normalized for token in statement.flatten() if token.ttype in sqlparse.tokens.Keyword}
        if statement.get_type() != 'SELECT' or keywords & forbidden:
            raise ValueError('El modo de consulta solo admite SELECT. Para otros comandos activa Permitir cambios y revisa la instrucción.')
    return statements[0]


def connection_url(config, allow_changes=False):
    c = config
    if c.motor == 'SQLite':
        path = Path(c.database).expanduser().resolve()
        if not path.is_file():
            raise ValueError('Selecciona una base SQLite existente. No se crea un archivo por accidente.')
        return URL.create('sqlite', database=path.as_uri(), query={'mode': 'rw' if allow_changes else 'ro', 'uri': 'true'}), {'timeout': 5}
    drivers = {'SQL Server': 'mssql+pyodbc', 'PostgreSQL': 'postgresql+pg8000', 'MySQL': 'mysql+pymysql', 'MariaDB': 'mariadb+pymysql', 'Oracle': 'oracle+oracledb'}
    if c.motor not in drivers:
        raise ValueError('Motor no reconocido.')
    if not c.host.strip() or not c.database.strip():
        raise ValueError('Completa servidor y base de datos o servicio.')
    query = {}
    args = {}
    database = c.database
    if c.motor == 'SQL Server':
        query = {'driver': c.driver, 'Encrypt': 'yes' if c.tls else 'no', 'TrustServerCertificate': 'no'}
        if not c.user:
            query['Trusted_Connection'] = 'yes'
        args = {'timeout': 10}
    elif c.motor == 'PostgreSQL':
        args = {'timeout': 15, 'ssl_context': ssl.create_default_context() if c.tls else False}
    elif c.motor in {'MySQL', 'MariaDB'}:
        args = {'connect_timeout': 10, 'read_timeout': 15, 'write_timeout': 15}
        if c.tls:
            args['ssl'] = ssl.create_default_context()
    elif c.motor == 'Oracle':
        query = {'service_name': database}
        database = None
        args = {'tcp_connect_timeout': 10}
        if c.tls:
            args['protocol'] = 'tcps'
    return URL.create(drivers[c.motor], username=c.user or None, password=c.password or None, host=c.host, port=c.port or (None if c.motor == 'SQL Server' and '\\' in c.host else PORTS[c.motor]), database=database, query=query), args


def safe_error(error, config):
    message = str(getattr(error, 'orig', error))
    if config.password:
        message = message.replace(config.password, '[contraseña oculta]')
    message = re.sub(r'(?i)(PWD|PASSWORD)\s*=\s*[^;\s]+', r'\1=[oculta]', message)
    return message[:1500]


def cell(value):
    if value is None:
        return None
    if isinstance(value, bytes):
        return f'[binario: {len(value)} bytes]'
    return str(value)[:2000]


def _odbc_quote(value):
    return '{' + value.replace('}', '}}') + '}'


class SqlManager:
    def __init__(self, config):
        self.config = config

    def perform(self, action, *, sql='', allow_changes=False, schema=None, table=None):
        if action == 'query':
            sql = validate_statement(sql, allow_changes)
        if self.config.motor == 'ODBC / DSN':
            return self._odbc(action, sql, allow_changes, schema, table)
        url, args = connection_url(self.config, allow_changes)
        engine = create_engine(url, connect_args=args, poolclass=NullPool, hide_parameters=True)
        try:
            with engine.connect() as connection:
                raw = connection.connection.driver_connection
                if self.config.motor == 'SQLite':
                    deadline = time.monotonic() + 15
                    raw.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
                elif self.config.motor == 'SQL Server':
                    raw.timeout = 15
                elif self.config.motor == 'Oracle':
                    raw.call_timeout = 15000
                if action == 'catalog':
                    inspector = inspect(connection)
                    schemas = inspector.get_schema_names()
                    chosen = schema or inspector.default_schema_name
                    tables = inspector.get_table_names(schema=chosen)
                    return {'motor': engine.dialect.name, 'version': str(engine.dialect.server_version_info), 'schemas': schemas, 'schema': chosen, 'tables': tables[:1000], 'tables_truncated': len(tables) > 1000}
                if action == 'columns':
                    columns = inspect(connection).get_columns(table, schema=schema)
                    return {'columns': [[c['name'], str(c['type']), str(c.get('nullable', ''))] for c in columns[:500]], 'table': table, 'schema': schema}
                if action != 'query':
                    raise ValueError('Operación SQL desconocida.')
                try:
                    if not allow_changes:
                        if self.config.motor == 'PostgreSQL':
                            connection.exec_driver_sql('SET TRANSACTION READ ONLY')
                            connection.exec_driver_sql("SET LOCAL statement_timeout = '15000ms'")
                        elif self.config.motor in {'MySQL', 'MariaDB'}:
                            connection.exec_driver_sql('SET TRANSACTION READ ONLY')
                    result = connection.exec_driver_sql(sql, execution_options={'no_parameters': True})
                    response = {'columns': [], 'rows': [], 'affected': result.rowcount, 'truncated': False, 'committed': allow_changes}
                    if result.returns_rows:
                        response['columns'] = list(result.keys())[:100]
                        rows = result.fetchmany(LIMIT + 1)
                        response['truncated'] = len(rows) > LIMIT or len(result.keys()) > 100
                        response['rows'] = [[cell(v) for v in row[:100]] for row in rows[:LIMIT]]
                    result.close()
                    if allow_changes:
                        connection.commit()
                    else:
                        connection.rollback()
                    return response
                except Exception:
                    connection.rollback()
                    raise
        finally:
            engine.dispose()

    def _odbc(self, action, sql, allow_changes, schema, table):
        import pyodbc
        c = self.config
        if not c.database.strip():
            raise ValueError('Selecciona o escribe el nombre de un DSN ODBC configurado en Windows.')
        dsn = 'DSN=' + _odbc_quote(c.database)
        if c.user:
            dsn += ';UID=' + _odbc_quote(c.user) + ';PWD=' + _odbc_quote(c.password)
        connection = pyodbc.connect(dsn, timeout=10, autocommit=False)
        connection.timeout = 15
        try:
            cursor = connection.cursor()
            if action == 'catalog':
                tables = cursor.tables(tableType='TABLE').fetchmany(1001)
                return {'motor': connection.getinfo(pyodbc.SQL_DBMS_NAME), 'version': connection.getinfo(pyodbc.SQL_DBMS_VER), 'schemas': sorted({row.table_schem for row in tables if row.table_schem}), 'schema': schema, 'tables': [row.table_name for row in tables if not schema or row.table_schem == schema][:1000]}
            if action == 'columns':
                rows = cursor.columns(table=table, schema=schema).fetchmany(500)
                return {'columns': [[r.column_name, r.type_name, str(r.nullable)] for r in rows], 'table': table, 'schema': schema}
            cursor.execute(sql)
            response = {'columns': [], 'rows': [], 'affected': cursor.rowcount, 'truncated': False, 'committed': allow_changes}
            if cursor.description:
                response['columns'] = [column[0] for column in cursor.description][:100]
                rows = cursor.fetchmany(LIMIT + 1)
                response['truncated'] = len(rows) > LIMIT or len(cursor.description) > 100
                response['rows'] = [[cell(v) for v in row[:100]] for row in rows[:LIMIT]]
            if allow_changes:
                connection.commit()
            else:
                connection.rollback()
            return response
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def backup_sqlite(source, destination):
    src = Path(source).resolve()
    dst = Path(destination).resolve()
    if src == dst or dst.exists():
        raise ValueError('Elige un archivo de respaldo nuevo, diferente del original.')
    handle = os.open(dst, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(handle)
    deadline = time.monotonic() + 30
    def progress(status, remaining, total):
        if time.monotonic() > deadline:
            raise TimeoutError('El respaldo excedió 30 segundos. Usa una herramienta de respaldo para bases grandes.')
    try:
        with closing(sqlite3.connect(src.as_uri() + '?mode=ro', uri=True, timeout=5)) as original:
            with closing(sqlite3.connect(dst, timeout=5)) as backup:
                original.backup(backup, pages=256, progress=progress)
                backup.commit()
                if backup.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise ValueError('No se pudo validar el respaldo.')
    except Exception:
        if dst.exists():
            dst.unlink()
        raise
    return str(dst)
