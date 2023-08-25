#!/bin/bash -e

buildinfo_h="Core/Inc/buildinfo.h"
buildinfo_py="gnwmanager/buildinfo.py"

TMPFILE=$(mktemp build/buildinfo.XXXXXX)
if [[ ! -e $TMPFILE ]]; then
    echo "Can't create tempfile!"
    exit 1
fi

GITHASH=$(git describe --always --dirty=+ 2> /dev/null || echo "NOGIT")
TIMESTAMP=$(date +%s)

echo -e "#ifndef GIT_HASH\n#define GIT_HASH \""${GITHASH}"\"\n#endif" > "${TMPFILE}"
echo -e "#ifndef BUILD_TIME\n#define BUILD_TIME "${TIMESTAMP}"\n#endif" >> "${TMPFILE}"

if ! diff -q ${TMPFILE} ${buildinfo_h} > /dev/null 2> /dev/null; then
    echo "Updating build info file ${buildinfo_h}"
    cp -f "${TMPFILE}" "${buildinfo_h}"
fi

rm -f "${TMPFILE}"

echo -e "GIT_HASH = u\""${GITHASH}"\"" > "${TMPFILE}"
echo -e "BUILD_TIME = "${TIMESTAMP} >> "${TMPFILE}"

if ! diff -q ${TMPFILE} ${buildinfo_py} > /dev/null 2> /dev/null; then
    echo "Updating build info file ${buildinfo_py}"
    cp -f "${TMPFILE}" "${buildinfo_py}"
fi

rm -f "${TMPFILE}"
