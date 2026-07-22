#!/data/data/com.termux/files/usr/bin/bash
# Titan Nova fast Termux control
# Install once:
#   cd ~/github && bash titanctl.sh install
# Then use:
#   github update
#   github restart
#   github stop
#   github status

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${TITAN_APP_DIR:-$SCRIPT_DIR}"
BACKUP_DIR="${TITAN_BACKUP_DIR:-$HOME/titan_backup}"

ok(){ printf '\033[1;32m%s\033[0m\n' "$*"; }
warn(){ printf '\033[1;33m%s\033[0m\n' "$*"; }
err(){ printf '\033[1;31m%s\033[0m\n' "$*"; }
info(){ printf '\033[1;36m%s\033[0m\n' "$*"; }

cd_app(){
  if [ ! -d "$APP_DIR" ]; then
    err "App folder nahi mila: $APP_DIR"
    echo "Folder create karne ke liye:"
    echo "  cd ~ && git clone https://github.com/kirannayakcontact-spec/Titan-nova-codex.git github"
    exit 1
  fi
  cd "$APP_DIR" || exit 1
}

need_deploy(){
  [ -f deploy.sh ] || { err "deploy.sh nahi mila. Repo folder galat hai: $APP_DIR"; exit 1; }
}

backup_titanctl(){
  mkdir -p "$BACKUP_DIR"
  if [ -f titanctl.sh ]; then
    cp -f titanctl.sh "$BACKUP_DIR/titanctl.sh.$(date +%s).bak" 2>/dev/null || true
  fi
}

clean_titanctl_before_pull(){
  # Agar local titanctl.sh edit ki wajah se pull block ho, pehle backup karke Git copy restore karo.
  backup_titanctl
  git checkout -- titanctl.sh >/dev/null 2>&1 || true
}

pull_latest(){
  cd_app
  command -v git >/dev/null 2>&1 || { err "git missing hai. Termux me: pkg install git"; exit 1; }
  info "GitHub update le raha hoon..."
  clean_titanctl_before_pull
  git pull origin main
}

run_deploy(){
  cd_app
  need_deploy
  bash deploy.sh "$1"
}

install_shortcuts(){
  cd_app
  mkdir -p "$HOME/bin"
  chmod +x "$APP_DIR/titanctl.sh" 2>/dev/null || true
  cat > "$HOME/bin/github" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
cd "$APP_DIR" || exit 1
bash "$APP_DIR/titanctl.sh" "\$@"
EOF
  cat > "$HOME/bin/titan" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
cd "$APP_DIR" || exit 1
bash "$APP_DIR/titanctl.sh" "\$@"
EOF
  chmod +x "$HOME/bin/github" "$HOME/bin/titan"
  if ! echo ":$PATH:" | grep -q ":$HOME/bin:"; then
    echo 'export PATH="$HOME/bin:$PATH"' >> "$HOME/.bashrc"
    export PATH="$HOME/bin:$PATH"
  fi
  ok "Shortcut ready: github update | github restart | github stop | github status"
  echo "Agar command turant na chale, Termux close/open karo ya run karo: source ~/.bashrc"
}

case "${1:-help}" in
  install)
    install_shortcuts
    ;;
  update|pull)
    pull_latest && run_deploy update
    ;;
  restart|start|run)
    run_deploy restart
    ;;
  stop)
    run_deploy stop
    ;;
  status)
    run_deploy status
    ;;
  full)
    pull_latest && run_deploy full
    ;;
  logs)
    cd_app
    tail -f flask.log gateway.log 2>/dev/null || true
    ;;
  help|--help|-h|*)
    echo "Titan Nova fast commands"
    echo "  bash titanctl.sh install   Install github/titan shortcut"
    echo "  github update              GitHub pull + fast restart"
    echo "  github restart             Fast restart only"
    echo "  github stop                Stop Flask/Gateway"
    echo "  github status              Show status"
    echo "  github full                Heavy install + full tests"
    ;;
esac
