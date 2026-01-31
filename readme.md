# Instagram Automation SaaS Platform

Production-ready Instagram comment-to-DM automation platform with payment processing, affiliate system, and admin panel.

## 🎯 Features

- **Instagram Integration**: OAuth authentication for Instagram Business/Creator/Private accounts
- **Comment Monitoring**: Real-time webhook-based comment detection
- **Auto DM Sending**: Automated keyword-triggered direct messages
- **Multi-Media Support**: Posts, Reels, Stories, and Live streams
- **Payment System**: Stripe integration with 15-day free trial
- **Affiliate Program**: 30% commission tracking and management
- **Admin Dashboard**: Complete system monitoring and user management
- **Rate Limiting**: Instagram API compliance and rate limit protection
- **Background Workers**: Celery-based async job processing

## 🏗️ Architecture

### Backend (Python FastAPI)
- RESTful API with FastAPI
- PostgreSQL database with SQLAlchemy ORM
- Redis for caching and queues
- Celery for background tasks
- Instagram Graph API integration
- Stripe payment processing
- JWT authentication

### Frontend (React)
- React 18 with React Router
- Tailwind CSS for styling
- Axios for API calls
- Context API for state management
- Protected routes and admin panel

## 📋 Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 15+
- Redis 7+
- Meta Developer Account
- Stripe Account

## 🚀 Quick Start

### 1. Clone Repository

```bash
git clone <repository-url>
cd instagram-automation-saas
```

### 2. Meta/Instagram Setup

1. Go to [Meta for Developers](https://developers.facebook.com/)
2. Create a new app and get App ID & App Secret
3. Enable Instagram API and configure permissions:
   - `instagram_basic`
   - `instagram_manage_messages`
   - `instagram_manage_comments`
4. Set up webhook endpoint (you'll use `/api/webhooks/instagram`)

### 3. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env

# Generate encryption key for Instagram tokens
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Add this to ENCRYPTION_KEY in .env

# Configure .env with your credentials
nano .env

# Initialize database
python -c "from app.database import engine, Base; from app.models import *; Base.metadata.create_all(bind=engine)"

# Run migrations (if using Alembic)
# alembic upgrade head
```

### 4. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Configure environment
echo "REACT_APP_API_URL=http://localhost:8000" > .env

# Start development server
npm start
```

### 5. Start Services

**Option A: Docker Compose (Recommended)**

```bash
# From project root
docker-compose up -d
```

**Option B: Manual Start**

Terminal 1 - Backend:
```bash
cd backend
uvicorn main:app --reload --port 8000
```

Terminal 2 - Celery Worker:
```bash
cd backend
celery -A app.workers.tasks worker --loglevel=info
```

Terminal 3 - Celery Beat:
```bash
cd backend
celery -A app.workers.tasks beat --loglevel=info
```

Terminal 4 - Frontend:
```bash
cd frontend
npm start
```

## 🔧 Configuration

### Environment Variables

#### Backend (.env)

```bash
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/instagram_automation

# Redis
REDIS_URL=redis://localhost:6379/0

# Meta/Instagram
META_APP_ID=your_app_id
META_APP_SECRET=your_app_secret
META_VERIFY_TOKEN=your_webhook_token

# JWT
JWT_SECRET_KEY=your_jwt_secret
JWT_ALGORITHM=HS256

# Stripe
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Trial & Pricing
FREE_TRIAL_DAYS=15
PRO_PLAN_PRICE=29.99

# Encryption (for Instagram tokens)
ENCRYPTION_KEY=your_44_character_fernet_key
```

#### Frontend (.env)

```bash
REACT_APP_API_URL=http://localhost:8000
```

## 📦 Database Schema

### Key Tables

- **users**: User accounts, Instagram credentials, subscription status
- **automations**: Automation configurations and statistics
- **dm_logs**: DM sending history and status
- **referrals**: Affiliate tracking
- **webhook_logs**: Instagram webhook event logs
- **rate_limit_trackers**: API rate limit tracking

## 🔐 Security

- Passwords hashed with bcrypt
- JWT tokens for authentication
- Instagram tokens encrypted with Fernet
- Stripe webhook signature verification
- Instagram webhook HMAC verification
- CORS protection
- Rate limiting

## 🌐 API Endpoints

### Authentication
- `POST /api/auth/register` - User registration
- `POST /api/auth/login` - User login
- `GET /api/auth/me` - Get current user
- `GET /api/auth/instagram/auth-url` - Get Instagram OAuth URL
- `POST /api/auth/instagram/callback` - Handle OAuth callback

### Automations
- `GET /api/automations/` - List automations
- `POST /api/automations/` - Create automation
- `GET /api/automations/{id}` - Get automation details
- `PUT /api/automations/{id}` - Update automation
- `DELETE /api/automations/{id}` - Delete automation
- `POST /api/automations/{id}/pause` - Pause automation
- `POST /api/automations/{id}/resume` - Resume automation

### Payments
- `GET /api/payments/subscription-status` - Check subscription
- `POST /api/payments/create-checkout-session` - Create Stripe session
- `POST /api/payments/webhook` - Stripe webhook handler
- `POST /api/payments/cancel-subscription` - Cancel subscription

### Admin
- `GET /api/admin/dashboard` - Admin metrics
- `GET /api/admin/users` - List all users
- `POST /api/admin/users/{id}/suspend` - Suspend user
- `POST /api/admin/users/{id}/extend-trial` - Extend trial

### Webhooks
- `GET /api/webhooks/instagram` - Verify webhook
- `POST /api/webhooks/instagram` - Handle Instagram events

## 🔄 Background Jobs

### Celery Tasks

- **process_comment_and_send_dm**: Process comments and send DMs
- **check_expired_trials**: Auto-disable expired trials (hourly)
- **check_failed_payments**: Handle payment failures (every 6 hours)
- **process_affiliate_commissions**: Calculate commissions (daily)

## 🧪 Testing

```bash
# Backend tests
cd backend
pytest

# Frontend tests
cd frontend
npm test
```

## 📊 Monitoring

- Check system health: `GET /api/admin/system-health`
- View webhook logs in database
- Monitor Celery tasks in Redis
- Check PostgreSQL logs

## 🚢 Deployment

### Production Checklist

1. Set `DEBUG=False` in backend .env
2. Use production database
3. Configure proper CORS origins
4. Set up SSL/TLS certificates
5. Use production Redis
6. Configure Stripe production keys
7. Set strong secret keys
8. Enable Celery monitoring (Flower)
9. Set up logging and monitoring
10. Configure backup strategy

### Deployment Platforms

- **Backend**: Railway, Render, AWS EC2, DigitalOcean
- **Frontend**: Vercel, Netlify, AWS S3 + CloudFront
- **Database**: AWS RDS, DigitalOcean Managed PostgreSQL
- **Redis**: Redis Cloud, AWS ElastiCache

## 📈 Scaling

- Use connection pooling for database
- Implement Redis caching
- Add multiple Celery workers
- Use load balancer for backend
- Implement CDN for frontend
- Database read replicas

## 🐛 Troubleshooting

### Instagram Connection Issues
- Verify Meta App permissions
- Check webhook subscription
- Validate access token expiration
- Review Instagram API rate limits

### Payment Issues
- Verify Stripe webhook endpoint
- Check webhook signature verification
- Review Stripe logs

### Background Job Issues
- Check Redis connection
- Review Celery worker logs
- Verify queue processing

## 📝 License

Proprietary - All rights reserved

## 👥 Support

For support and inquiries, contact: support@yourdomain.com

## 🎓 Documentation

- [Instagram Graph API](https://developers.facebook.com/docs/instagram-api/)
- [Stripe API](https://stripe.com/docs/api)
- [FastAPI](https://fastapi.tiangolo.com/)
- [React](https://react.dev/)

---

Built with ❤️ for Instagram automation

```
Dmtest-main
├─ .dockerignore
├─ Dockerfile
├─ alembic
│  ├─ README
│  ├─ env.py
│  ├─ script.py.mako
│  └─ versions
│     └─ 59008a36739b_initial_schema.py
├─ alembic.ini
├─ app
│  ├─ __init__.py
│  ├─ admin
│  │  ├─ __init__.py
│  │  └─ routes.py
│  ├─ affiliates
│  │  ├─ __init__.py
│  │  └─ routes.py
│  ├─ auth
│  │  ├─ __init__.py
│  │  ├─ routes.py
│  │  └─ utils.py
│  ├─ automations
│  │  ├─ __init__.py
│  │  └─ routes.py
│  ├─ config.py
│  ├─ database.py
│  ├─ instagram
│  │  ├─ __init__.py
│  │  ├─ routes.py
│  │  ├─ service.py
│  │  └─ webhooks.py
│  ├─ models.py
│  ├─ payments
│  │  ├─ __init__.py
│  │  └─ routes.py
│  └─ workers
│     ├─ __init__.py
│     └─ tasks.py
├─ backend
│  ├─ Dockerfile
│  ├─ app
│  │  ├─ __init__.py
│  │  ├─ admin
│  │  │  ├─ __init__.py
│  │  │  └─ routes.py
│  │  ├─ affiliates
│  │  │  ├─ __init__.py
│  │  │  └─ routes.py
│  │  ├─ auth
│  │  │  ├─ __init__.py
│  │  │  ├─ routes.py
│  │  │  └─ utils.py
│  │  ├─ automations
│  │  │  ├─ __init__.py
│  │  │  └─ routes.py
│  │  ├─ config.py
│  │  ├─ database.py
│  │  ├─ instagram
│  │  │  ├─ __init__.py
│  │  │  ├─ routes.py
│  │  │  ├─ service.py
│  │  │  └─ webhooks.py
│  │  ├─ models.py
│  │  ├─ payments
│  │  │  ├─ __init__.py
│  │  │  └─ routes.py
│  │  └─ workers
│  │     ├─ __init__.py
│  │     └─ tasks.py
│  ├─ celerybeat-schedule
│  ├─ main.py
│  └─ requirements.txt
├─ celerybeat-schedule
├─ dmrocket
├─ dmrocket.pub
├─ docker-compose.yml
├─ main.py
├─ readme.md
└─ requirements.txt

```
```
Dmtest-main
├─ .dockerignore
├─ Dockerfile
├─ alembic
│  ├─ README
│  ├─ env.py
│  ├─ script.py.mako
│  └─ versions
│     └─ 59008a36739b_initial_schema.py
├─ alembic.ini
├─ app
│  ├─ __init__.py
│  ├─ admin
│  │  ├─ __init__.py
│  │  └─ routes.py
│  ├─ affiliates
│  │  ├─ __init__.py
│  │  └─ routes.py
│  ├─ auth
│  │  ├─ __init__.py
│  │  ├─ routes.py
│  │  └─ utils.py
│  ├─ automations
│  │  ├─ __init__.py
│  │  └─ routes.py
│  ├─ config.py
│  ├─ database.py
│  ├─ instagram
│  │  ├─ __init__.py
│  │  ├─ routes.py
│  │  ├─ service.py
│  │  └─ webhooks.py
│  ├─ models.py
│  ├─ payments
│  │  ├─ __init__.py
│  │  └─ routes.py
│  └─ workers
│     ├─ __init__.py
│     └─ tasks.py
├─ celerybeat-schedule
├─ dmrocket
├─ dmrocket.pub
├─ docker-compose.yml
├─ main.py
├─ readme.md
└─ requirements.txt

```