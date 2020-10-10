#!/bin/bash
#
# Create pypy3 environment to run against oclz syncer. This is a backup run mode
# on systems where you aren't allowed to install docker.
#
# It fetches pypy 3.7 binaries and sets it up in the ../pypy3 folder.

# Set working directory to script location.
cd "${0%/*}"

readonly WORKSPACE="./"
readonly TARGET_DIR="../pypy3"
readonly PYPY_BINARY="${TARGET_DIR}/bin/pypy"
readonly REQUIREMENTS_TXT="../requirements.txt"

function setup_and_install() {
    # Create a super clean start.
    rm -rf "${TARGET_DIR}"

    DOWNLOAD_NAME="pypy3.7-v7.3.2-linux64"
    DOWNLOAD_FILE="${DOWNLOAD_NAME}.tar.bz2"
    DOWNLOAD_LINK="https://downloads.python.org/pypy/${DOWNLOAD_FILE}"

    # Download binary for pypy.
    wget ${DOWNLOAD_LINK} -P "${WORKSPACE}"
    # Extract and creates a folder caled ${DOWNLOAD_NAME}.
    tar xvjf "${WORKSPACE}${DOWNLOAD_FILE}"
    # Rename to pypy3.
    mv "${WORKSPACE}${DOWNLOAD_NAME}" "${TARGET_DIR}"
    # Cleanup downloaded binary.
    rm "${DOWNLOAD_FILE}"
    
    # Install pip!
    $PYPY_BINARY -m ensurepip --user
    $PYPY_BINARY -m pip install --user --upgrade pip

    # Install requirements
    $PYPY_BINARY -m pip install -r "${REQUIREMENTS_TXT}"
}

# Check first if pypy already exists instead of starting from scratch.
if [ ! -f "${PYPY_BINARY}" ]; then
    echo "pypy is missing! Starting install..."
    setup_and_install
fi

# Run the syncer!
$PYPY_BINARY ../main.py $@
