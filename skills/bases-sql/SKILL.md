---
name: Bases de datos SQL
description: Preparar SQL para SQL Server, PostgreSQL, MySQL/MariaDB, SQLite, Oracle y ODBC con revisión antes de ejecutar.
---
Confirma el motor y su versión antes de proponer sintaxis específica. No prometas compatibilidad universal.
Usa el esquema que el usuario comparta; nunca inventes tablas o columnas. Si falta, solicita la estructura.
Entrega una propuesta SQL en un bloque sql, con explicación sencilla de su efecto. La ejecución pertenece al panel SQL y requiere revisión del usuario.
Nunca solicites contraseñas en el chat. No guardes credenciales en archivos o memoria.
Para cambios, propone primero SELECT que muestre qué filas se afectarían, un WHERE preciso y un respaldo probado. Describe cuando DDL puede confirmar cambios automáticamente.
No presentes exportar 500 filas como respaldo completo. Para respaldos completos usa herramientas nativas del motor, comprueba errores y recomienda probar la restauración en una base separada.
No desactives TLS o la comprobación de certificados para resolver conexiones. Identifica el controlador y las versiones realmente probadas.
