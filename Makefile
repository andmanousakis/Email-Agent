.PHONY: help tree demo stack stack-build stack-up stack-down clean-all clean-demo clean-python clean-demo-all clean-python-all

help:
	@echo ""
	@echo "Available commands:"
	@echo ""
	@echo "  make help        - Show available commands"
	@echo "  make tree        - Show project structure"
	@echo ""
	@echo "Docker Compose:"
	@echo "  make stack-build-up  - Build + start compose stack"
	@echo "  make stack-build     - Build compose services"
	@echo "  make stack-up        - Start agent + UI stack"
	@echo "  make stack-down      - Stop compose stack"
	@echo ""
	@echo "Docker cleanup:"
	@echo "  make clean-all        - Remove ALL containers and images"

tree:
	@echo ""
	@echo "Project structure:"
	@echo ""
	@tree -I '__pycache__|*.pyc|.git'

# -------------------------
# DOCKER COMPOSE STACK
# -------------------------

stack-build:
	@echo ""
	@echo "Building compose services..."
	@docker compose -f docker/docker-compose.yml build

stack-up:
	@echo ""
	@echo "Starting agent + UI..."
	@docker compose -f docker/docker-compose.yml up

stack-build-up:
	@echo ""
	@echo "Building and starting stack..."
	@docker compose -f docker/docker-compose.yml down
	@docker compose -f docker/docker-compose.yml up --build
	@docker image prune -f

stack-down:
	@echo ""
	@echo "Stopping compose stack..."
	@docker compose -f docker/docker-compose.yml down

# -------------------------
# CLEAN EVERYTHING
# -------------------------

clean-all:
	@echo "Removing project containers..."
	@docker rm -f $$(docker ps -aq --filter ancestor=email-agent) 2>/dev/null || true
	@docker rm -f $$(docker ps -aq --filter ancestor=email-agent-ui) 2>/dev/null || true
	@echo "Removing project images..."
	@docker rmi -f email-agent email-agent-ui 2>/dev/null || true
	@echo "Removing dangling images..."
	@docker image prune -f
