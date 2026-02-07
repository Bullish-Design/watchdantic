{ pkgs, lib, config, inputs, ... }:

{
  # https://devenv.sh/basics/
  env.GREET = "devenv";

  packages = with pkgs; [
    uv
    python312
    wl-clipboard
    xclip
    xsel
  ];

  # Ensure uv prefers this interpreter
  env = {
    UV_PYTHON = "${pkgs.python312}/bin/python3";
  };

  
  # Optional convenience command: `cliplog [args...]`
  scripts.cliplog.exec = ''
    uv run src/scripts/clipboard_filegen.py "$@"
  '';

  # Optional: quick visibility on backends when you enter
  enterShell = ''
    echo "[devenv] python: $(python3 --version)"
    command -v wl-paste >/dev/null && echo "[devenv] wl-paste available" || true
    command -v xclip >/dev/null && echo "[devenv] xclip available" || true
    command -v xsel  >/dev/null && echo "[devenv] xsel  available" || true
  '';
  # Enable dotenv for populating environment variables: 
  #dotenv.enable = true;

  # https://devenv.sh/languages/
  # languages.rust.enable = true;
  languages.python = {
    enable = true;
    version = "3.13";
    venv.enable = true;
    uv.enable = true;
  };
  # https://devenv.sh/processes/
  # processes.cargo-watch.exec = "cargo-watch";

  # https://devenv.sh/services/
  # services.postgres.enable = true;

  # https://devenv.sh/scripts/
  scripts.hello.exec = ''
    echo hello from $GREET
  '';

  
  # https://devenv.sh/tasks/
  # tasks = {
  #   "myproj:setup".exec = "mytool build";
  #   "devenv:enterShell".after = [ "myproj:setup" ];
  # };
  
  # https://devenv.sh/tests/
  enterTest = ''
    echo "Running tests"
    git --version | grep --color=auto "${pkgs.git.version}"
  '';

  # https://devenv.sh/git-hooks/
  # git-hooks.hooks.shellcheck.enable = true;

  # See full reference at https://devenv.sh/reference/options/
}
