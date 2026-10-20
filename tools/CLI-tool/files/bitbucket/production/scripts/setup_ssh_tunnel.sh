#!/bin/bash
# Opens an SSH port forward (8080) to the remote Kubeflow cluster.
# Required Pipelines variables: REMOTE_CLUSTER_SSH_PRIVATE_KEY_B64, REMOTE_CLUSTER_SSH_IP,
# REMOTE_CLUSTER_SSH_USERNAME (set by the CLI tool as workspace variables).
set -e
echo "🔐 Configuring SSH Client..."
apt-get update -y && apt-get install -y openssh-client
mkdir -p ~/.ssh

if [ -z "$REMOTE_CLUSTER_SSH_IP" ]; then
  echo "❌ CRITICAL ERROR: REMOTE_CLUSTER_SSH_IP is empty. Stopping pipeline."; exit 1
fi
if [ -z "$REMOTE_CLUSTER_SSH_PRIVATE_KEY_B64" ]; then
  echo "❌ CRITICAL ERROR: REMOTE_CLUSTER_SSH_PRIVATE_KEY_B64 is empty. Stopping pipeline."; exit 1
fi

(umask 077; echo "$REMOTE_CLUSTER_SSH_PRIVATE_KEY_B64" | base64 --decode > ~/.ssh/id_rsa)
ssh-keyscan -H "$REMOTE_CLUSTER_SSH_IP" >> ~/.ssh/known_hosts

echo "🔗 Establishing SSH Port Forwarding to Remote Cluster (8080)..."
ssh -i ~/.ssh/id_rsa -L 8080:127.0.0.1:8080 -o StrictHostKeyChecking=no -o BatchMode=yes \
  "$REMOTE_CLUSTER_SSH_USERNAME@$REMOTE_CLUSTER_SSH_IP" -N -f
sleep 5
