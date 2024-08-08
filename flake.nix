{
  inputs = {
    flake-compat.url = "https://flakehub.com/f/edolstra/flake-compat/*.tar.gz";
    flake-schemas.url = "https://flakehub.com/f/DeterminateSystems/flake-schemas/*.tar.gz";
    nixpkgs.url = "https://flakehub.com/f/NixOS/nixpkgs/*.tar.gz";

    rust-overlay = {
      url = "github:oxalica/rust-overlay";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, flake-compat, flake-schemas, nixpkgs, rust-overlay }:
    let
      # Nixpkgs overlays
      overlays = [(import rust-overlay)];      # Helpers for producing system-specific outputs
      supportedSystems = [ "aarch64-darwin"];
      forEachSupportedSystem = f: nixpkgs.lib.genAttrs supportedSystems (system: f {
        pkgs = import nixpkgs { 
          inherit overlays system; 
          # config.allowBroken = true;
          config.permittedInsecurePackages = ["openssl-1.1.1w"];
        };
        
      });
    in {
      # Schemas tell Nix about the structure of your flake's outputs
      schemas = flake-schemas.schemas;

      # Development environments
      devShells = forEachSupportedSystem ({ pkgs }: {
          default = pkgs.mkShell {
          # Pinned packages available in the environment
          packages = with pkgs; [
            rust-bin.stable."1.78.0".default
            cargo-bloat
            cargo-edit
            cargo-outdated
            cargo-udeps
            cargo-watch
            rust-analyzer
            SDL2
            curl
            openssl_1_1
            libiconv
            cmake
            gcc
            google-cloud-sdk
          ];
          

          # Environment variables
          env = {
            # RUST_BACKTRACE = "1";
            # CC= "/usr/bin/clang";
            # CXX="/usr/bin/clang++";
            # AR="/usr/bin/ar";
            # RANLIB="/usr/bin/ranlib";
            # PKG_CONFIG_PATH = "${pkgs.openssl.dev}/lib/pkgconfig";
          };
        };
      });
    };
}
