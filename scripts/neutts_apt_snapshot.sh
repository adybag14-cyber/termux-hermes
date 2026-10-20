#!/usr/bin/env bash
# Source-only native APT bootstrap. Python is not available before foundation.
# Callers use set -Eeuo pipefail and own/remove the supplied fresh work directory.

neutts_apt_file() {
  local file="$1" bytes="$2" sha="$3"
  [[ -f "$file" && ! -L "$file" && "$(stat -c %s "$file")" == "$bytes" ]] || {
    echo "Missing, linked or wrong-size original APT input: $file" >&2; return 1;
  }
  printf '%s  %s\n' "$sha" "$file" | sha256sum -c - >/dev/null
}

neutts_apt_known_pins() {
  local pins="$1" actual
  [[ -f "$pins" && ! -L "$pins" ]] || return 1
  read -r actual _ < <(sha256sum "$pins")
  case "$actual" in
    7ad635d7f1ce1157c7f3b3d7808eaf113c8bb77c4e99a8fe30b6b155faf04c5e|83e67a558d1322b8ea55c2d3d885e0dde9725e54694faa490f3ea16064978af3) ;;
    *) echo "Original foundation/compiler pin set changed" >&2; return 1 ;;
  esac
}

neutts_apt_snapshot_open() {
  local inputs="$1" work="$2" evidence="$3"
  local name version arch sha bytes archive_path original portable source count
  local repo="$work/signed-repository" lists="$work/apt-lists"
  [[ -d "$inputs" && ! -L "$inputs" && ! -e "$work" && ! -e "$evidence" ]] || {
    echo "Use original prepared inputs and fresh snapshot work/evidence directories" >&2; return 1;
  }
  # APT's config/source grammars are deliberately narrower than shell paths.
  [[ "$work" =~ ^/[A-Za-z0-9_./-]+$ ]] || { echo "Unsafe native APT work path" >&2; return 1; }
  [[ -d "$inputs/snapshot" && ! -L "$inputs/snapshot" &&
     -d "$inputs/apt-archives" && ! -L "$inputs/apt-archives" ]] || return 1
  neutts_apt_file "$inputs/foundation.tsv" 18469 7ad635d7f1ce1157c7f3b3d7808eaf113c8bb77c4e99a8fe30b6b155faf04c5e
  neutts_apt_file "$inputs/snapshot/InRelease" 14016 249dab3ab3da3993b2436d48c819506f9aa586f6985905d81a451e76f2de7901
  neutts_apt_file "$inputs/snapshot/Packages.gz" 727968 dba73c2f0caaa828b65f02ba0e56cac694ee7186999a442ae7858b4258c321b6
  mkdir -p "$repo/dists/stable/main/binary-aarch64" "$lists/partial" "$evidence"
  cat "$inputs/foundation.tsv" > "$work/selected.tsv"
  if [[ -e "$inputs/compiler.tsv" || -L "$inputs/compiler.tsv" ]]; then
    neutts_apt_file "$inputs/compiler.tsv" 6581 83e67a558d1322b8ea55c2d3d885e0dde9725e54694faa490f3ea16064978af3
    cat "$inputs/compiler.tsv" >> "$work/selected.tsv"
  fi
  LC_ALL=C sort -u "$work/selected.tsv" > "$work/selected-sorted.tsv"
  [[ -f "$inputs/ARCHIVES.tsv" && ! -L "$inputs/ARCHIVES.tsv" ]]
  cmp "$work/selected-sorted.tsv" "$inputs/ARCHIVES.tsv"
  count=0
  while IFS=$'\t' read -r name version arch sha bytes archive_path; do
    original="${name}_${version}_${arch}.deb"
    portable="${original//:/%3A}"
    source="$inputs/apt-archives/$portable"
    neutts_apt_file "$source" "$bytes" "$sha"
    # The original signed pool path is unchanged. Only the portable input
    # basename and writable APT cache basename use percent-encoded epochs.
    mkdir -p "$repo/$(dirname "$archive_path")"
    ln -s "$(realpath "$source")" "$repo/$archive_path"
    count=$((count + 1))
  done < "$work/selected-sorted.tsv"
  local -a input_archives=()
  shopt -s nullglob
  input_archives=("$inputs/apt-archives/"*)
  [[ "${#input_archives[@]}" == "$count" && ( "$count" == 122 || "$count" == 141 ) ]] || {
    echo "Prepared APT archive inventory changed" >&2; return 1;
  }
  cp "$inputs/snapshot/InRelease" "$repo/dists/stable/InRelease"
  cp "$inputs/snapshot/Packages.gz" "$repo/dists/stable/main/binary-aarch64/Packages.gz"
  "$PREFIX/lib/apt/apt-helper" cat-file "$inputs/snapshot/Packages.gz" > "$work/expected-Packages"
  neutts_apt_file "$work/expected-Packages" 1867286 95cf6e3b7cf347a81aef44e45199724b7a6cd21c29be7611cc1ac5ebaf2640e1
  printf 'deb [arch=aarch64] file://%s stable main\n' "$repo" > "$work/frozen.list"
  cat > "$work/frozen.conf" <<APT_CONFIG_EOF
Dir::Etc::sourcelist "$work/frozen.list";
Dir::Etc::sourceparts "-";
Dir::State::lists "$lists";
Acquire::Languages "none";
Acquire::AllowInsecureRepositories "false";
Acquire::AllowDowngradeToInsecureRepositories "false";
Acquire::AllowWeakRepositories "false";
APT::Get::AllowUnauthenticated "false";
APT::Update::Error-Mode "any";
APT_CONFIG_EOF
  export APT_CONFIG="$work/frozen.conf"
  if ! apt-get update > "$evidence/apt-update.log" 2>&1; then
    cat "$evidence/apt-update.log" >&2
    return 1
  fi
  local -a releases=("$lists/"*_InRelease)
  local -a indexes=("$lists/"*_Packages "$lists/"*_Packages.lz4 "$lists/"*_Packages.gz)
  [[ "${#releases[@]}" == 1 && "${#indexes[@]}" == 1 ]] || {
    echo "APT did not acquire exactly one authenticated release/index" >&2; return 1;
  }
  neutts_apt_file "${releases[0]}" 14016 249dab3ab3da3993b2436d48c819506f9aa586f6985905d81a451e76f2de7901
  "$PREFIX/lib/apt/apt-helper" cat-file "${indexes[0]}" \
    > "$work/acquired-Packages" 2> "$evidence/apt-index-read.stderr.log"
  [[ ! -s "$evidence/apt-index-read.stderr.log" ]]
  cmp "$work/expected-Packages" "$work/acquired-Packages"
  cp "${releases[0]}" "$evidence/InRelease"
  cp "$inputs/snapshot/Packages.gz" "$evidence/Packages.gz"
  cp "$work/frozen.list" "$work/frozen.conf" "$evidence/"
  printf '{"schema":"neutts-native-frozen-apt/v1","status":"passed","authority":"native APT configured trust store","insecure_repository_exceptions":false,"acquired_index_bytes_equal":true,"archive_count":%s,"inrelease_sha256":"249dab3ab3da3993b2436d48c819506f9aa586f6985905d81a451e76f2de7901","packages_gz_sha256":"dba73c2f0caaa828b65f02ba0e56cac694ee7186999a442ae7858b4258c321b6","packages_uncompressed_sha256":"95cf6e3b7cf347a81aef44e45199724b7a6cd21c29be7611cc1ac5ebaf2640e1","release_output":false}\n' \
    "$count" > "$evidence/RESULT.json"
}

neutts_apt_stage_archives() {
  local inputs="$1" pins="$2" destination="$3" ledger="$4"
  local name version arch sha bytes archive_path original portable native source target count=0
  neutts_apt_known_pins "$pins"
  [[ ! -e "$destination" && ! -L "$destination" && ! -e "$ledger" ]] || {
    echo "Use a fresh native archive cache and ledger" >&2; return 1;
  }
  mkdir -p "$destination/partial"
  : > "$ledger"
  while IFS=$'\t' read -r name version arch sha bytes archive_path; do
    original="${name}_${version}_${arch}.deb"
    portable="${original//:/%3A}"
    native="${original//:/%3a}"
    source="$inputs/apt-archives/$portable"
    target="$destination/$native"
    neutts_apt_file "$source" "$bytes" "$sha"
    cp "$source" "$target"
    neutts_apt_file "$target" "$bytes" "$sha"
    [[ "$(dpkg-deb -f "$target" Package)" == "$name" ]]
    [[ "$(dpkg-deb -f "$target" Version)" == "$version" ]]
    [[ "$(dpkg-deb -f "$target" Architecture)" == "$arch" ]]
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$name" "$version" "$arch" "$archive_path" "$portable" "$native" "$bytes" "$sha" >> "$ledger"
    count=$((count + 1))
  done < "$pins"
  local -a copied=("$destination/"*.deb)
  [[ "${#copied[@]}" == "$count" ]]
}

neutts_apt_validate_plan() {
  local plan="$1" pins="$2"
  neutts_apt_known_pins "$pins"
  awk '
    NR == FNR { split($0, row, "\t"); wanted[row[1]] = row[2]; expected++; next }
    /^Remv / { print "APT proposed a removal" > "/dev/stderr"; bad = 1 }
    /^Inst / {
      name = $2; sub(/:[a-z0-9-]+$/, "", name)
      version = ""
      for (i = 3; i <= NF; i++) {
        if (substr($i, 1, 1) == "(") { version = substr($i, 2); break }
      }
      if (!(name in wanted) || seen[name]++ || version != wanted[name]) {
        print "APT proposed an extra, duplicate or different package: " name > "/dev/stderr"; bad = 1
      }
      actual++
    }
    END {
      if (actual != expected) { print "APT omitted or added a pinned package" > "/dev/stderr"; bad = 1 }
      for (name in wanted) if (seen[name] != 1) bad = 1
      exit bad
    }
  ' "$pins" "$plan"
}
