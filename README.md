# AI Talk Builder

AI Talk Builder is a Flask web app for creating, refining, and viewing meeting talks with structured OpenAI assistance. It is designed for personal or small-group use on a self-managed Ubuntu VPS.

## Stack

- Flask app factory
- PostgreSQL with SQLAlchemy
- Flask-Migrate / Alembic
- Flask-Login session auth
- HTML templates, CSS, and vanilla JavaScript
- OpenAI Responses API with structured parsing

## Quick start

1. Create a virtual environment and install dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and update secrets:

   ```bash
   cp .env.example .env
   ```

3. Set up the database:

   ```bash
   flask db init
   flask db migrate -m "Initial schema"
   flask db upgrade
   ```

4. Create the first admin:

   ```bash
   flask create-admin
   ```

5. Run locally:

   ```bash
   flask run
   ```

## Features

- Username or email login
- Admin and regular user roles
- Manual password reset workflow with admin-generated temporary passwords
- Talk CRUD, settings, section editor, and view/export mode
- Reference file uploads stored on disk with metadata in PostgreSQL
- AI full generation, global revision, and section-only revision
- Talk-level revision prompt plus section-specific revision prompts for iterative rewrites
- Live word and timing calculations in the editor

## OpenAI integration

`/Users/danielbaker/apps/talk/app/services/openai_service.py` centralizes prompt construction, reference file extraction, structured response parsing, and error handling.

The app is currently hard-locked to `gpt-5.5` for talk generation and revision so it does not silently fall back to a weaker model.

Iteration behavior:

- `Base prompt` defines the original generation goal for the talk.
- `Talk-level revision prompt` lets you steer whole-talk rewrites across multiple sections.
- `Section prompt / refinement instruction` lets you target specific sections.
- If no talk-level or section-level revision prompts changed, the editor warns before rerunning the same AI update.
- Frozen sections stay in context but are not supposed to be rewritten.

The implementation uses the OpenAI Python SDK's Responses API and structured parsing support. OpenAI's docs show `client.responses.create(...)` as the recommended Python entry point and document structured parsing via `client.responses.parse(..., text_format=YourPydanticModel)` for schema-safe output. Sources:

- [OpenAI SDKs and CLI docs](https://developers.openai.com/api/docs/libraries)
- [OpenAI structured outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs)

## Suggested Ubuntu deployment

1. Install system packages:

   ```bash
   sudo apt update
   sudo apt install python3-venv python3-pip postgresql postgresql-contrib nginx
   ```

2. Create a PostgreSQL database and user.
3. Clone the repo onto the VPS and configure `.env`.
4. Run migrations and create the admin.
5. Launch Gunicorn:

   ```bash
   gunicorn -c deploy/gunicorn.conf.py wsgi:app
   ```

6. Put Nginx in front of Gunicorn as a reverse proxy.

Sample deployment files are included in `/Users/danielbaker/apps/talk/deploy`:

- [deploy/gunicorn.conf.py](/Users/danielbaker/apps/talk/deploy/gunicorn.conf.py)
- [deploy/systemd/ai-talk-builder.service](/Users/danielbaker/apps/talk/deploy/systemd/ai-talk-builder.service)
- [deploy/nginx/ai-talk-builder.conf](/Users/danielbaker/apps/talk/deploy/nginx/ai-talk-builder.conf)

Example systemd setup:

```bash
sudo cp deploy/systemd/ai-talk-builder.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ai-talk-builder
sudo systemctl start ai-talk-builder
```

Example Nginx setup:

```nginx
server {
    listen 80;
    server_name your-domain.example;

    client_max_body_size 16M;

    location /static/ {
        alias /home/ubuntu/ai-talk-builder/app/static/;
        expires 7d;
        add_header Cache-Control "public";
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 180;
    }
}
```

Then enable the site:

```bash
sudo cp deploy/nginx/ai-talk-builder.conf /etc/nginx/sites-available/ai-talk-builder
sudo ln -s /etc/nginx/sites-available/ai-talk-builder /etc/nginx/sites-enabled/ai-talk-builder
sudo nginx -t
sudo systemctl reload nginx
```

## Notes

- The temporary password is intentionally visible to admins in the management view to match the requested manual handoff workflow.
- Uploaded files are capped at 16 MB by default.
- For production, store `SECRET_KEY` and `OPENAI_API_KEY` only in environment-backed secrets.
- Because `Talk.global_revision_prompt` was added after the first scaffold, run a new migration before deploying updated code.
