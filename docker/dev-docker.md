```bash
echo $(pwd)
```

```bash
docker run -d \
  --name postgres-vector \
  --restart always \
  -p ${PG_PORT:-27429}:5432 \
  -e POSTGRES_DB="${POSTGRES_DB:-telegram_dify_bot}" \
  -e POSTGRES_USER="${POSTGRES_USER:-postgres}" \
  -e POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-YHMovFEM82o4Ys6n}" \
  -e PGDATA="/var/lib/postgresql/data/pgdata" \
  -e TZ="Asia/Shanghai" \
  -v "$(pwd)/volumes/postgres_data:/var/lib/postgresql/data" \
  -v "$(pwd)/volumes/postgres/logs:/var/log/postgresql" \
  pgvector/pgvector:pg17
```