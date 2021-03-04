#!/bin/bash

# Copyright (C) 2015 SignalFx, Inc. All rights reserved.

# Helper script to perform a release of MaestroNG and publish it on GitHub and
# PyPI.
#
# Usage: ./release.sh <version>
#
# If the NO_PUBLISH environment variable is non-empty, nothing will leave this
# host (no branch push, no tag push, no release upload to PyPI).
# To revert a non-published release, remove the tag and reset to the previous
# commit: `git tag -d maestro-${version} && git reset --hard "HEAD^"`

function log() {
  local msg=${1}
  shift
  echo -e $* "\033[;1m${msg}\033[;0m"
}

function warn() {
  local msg=${1}
  shift
  echo -e $* "\033[31;1m${msg}\033[;0m"
}

if [ $# -ne 1 ] ; then
  echo "usage: $0 <version>"
  exit 1
fi

log "Preparing MaestroNG release v${1}..."

# Make sure we have the latest version of the release tools.
log "Upgrading release tools..."
pip install --upgrade pip setuptools wheel twine

# Update the version in version.py.
log "Setting package version to ${1}..."
sed -e "s/^version = .*/version = '${1}'/" -i "" maestro/version.py

# Final review
echo
log "Please review release changes:"
git diff
echo

log "Confirm? [y/N] " -n
read confirm
if [ "${confirm}" != "y" ] ; then
  warn "Aborted release. Cleaning up..."
  git checkout maestro/version.py
  exit 1
fi

# Commit and push release commit.
log "Committing changes..."
git commit -a -s -m "Maestro ${1}"
if [ -z "${NO_PUBLISH}" ] ; then
  git push origin main
else
  warn "Skipped branch push"
fi

# Tag the release and publish the tag.
tag="maestro-${1}"
log "Tagging release ${tag}..."
git tag -a -f -m "Maestro-NG version ${1}" maestro-${1}
if [ -z "${NO_PUBLISH}" ] ; then
  git push --tags
else
  warn "Skipped tag push"
fi

# Build and upload the release to PyPI.
log "Building and uploading release wheel..."
python setup.py bdist_wheel
if [ -z "${NO_PUBLISH}" ] ; then
  twine upload dist/maestro_ng-${1}-py2.py3-none-any.whl
else
  warn "Skipped release deploy"
fi

log "Maestro v${1} is now released."
