{ pkgs }:
pkgs.mkShell {
  # Add build dependencies
  packages = [ pkgs.python312 pkgs.python312Packages.pip ];

  # Add environment variables
  env = { };

  # Load custom bash code
  shellHook = ''

  '';
}
