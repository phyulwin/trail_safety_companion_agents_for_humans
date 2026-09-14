#!/bin/sh
# bootstrap.sh - Install Docker on an Ubuntu 24.04 Lightsail instance.
set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io docker-compose-v2
systemctl enable --now docker
usermod -aG docker ubuntu
mkdir -p /opt/trail
chown ubuntu:ubuntu /opt/trail
# Small-instance builds need swap; the persistent database remains on disk.
if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
