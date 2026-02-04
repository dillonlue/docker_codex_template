# Rebuild the image after changing Dockerfile/dependencies
source ./set_project_env.sh
docker-compose build

# Start the container in the background
docker-compose up -d

# Docker can use lots of memory on computer either by keeping old images or build cache
# to see how much memory run:
# docker system df
# To prune all memory run: docker system prune -af --volumes
