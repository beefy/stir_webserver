# stir_webserver

## Setup

### Prerequisites

- Python 3.10+
- MongoDB (local or remote instance)

### Installation

1. Clone the repository:
   ```bash
   git clone <repo-url>
   cd stir_webserver
   ```

2. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Copy the environment file and adjust as needed:
   ```bash
   cp .env.example .env
   ```

### Database Migrations

This project uses [Beanie](https://beanie-odm.dev/) — an async MongoDB ODM
for Python — to manage database migrations.

#### Running Migrations

Make sure `PYTHONPATH` includes the project root, then run:

```bash
# Apply all pending migrations
PYTHONPATH=. python3 scripts/migrate.py up

# Roll back all migrations
PYTHONPATH=. python3 scripts/migrate.py down
```

#### Configuration

The migration runner reads the following environment variables:

| Variable | Default | Description |
|---|---|---|
| `MONGODB_CONNECTION_STRING` | `mongodb://localhost:27017` | MongoDB connection URI |
| `MONGODB_DATABASE_NAME` | `stir_webserver` | Target database name |

Example with custom connection string:

```bash
MONGODB_CONNECTION_STRING="mongodb+srv://user:pass@cluster.mongodb.net" \
MONGODB_DATABASE_NAME="stir_prod" \
PYTHONPATH=. \
python3 scripts/migrate.py up
```

#### Adding New Migrations

1. Create a new file in the `migrations/` directory following the naming
   convention `NNN_description.py` (e.g., `002_add_indexes.py`).
2. Define `async def upgrade(connection_string, database_name)` and
   `async def downgrade(connection_string, database_name)` functions.
3. Migrations are discovered automatically — no registration needed.

### Running the Server

```bash
PYTHONPATH=. uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`. Interactive docs
are at `http://localhost:8000/docs`.
