#!/bin/bash
set -x

SCRIPT_PATH=$(dirname `which $0`)

apt-get install -y git python-pip

cd $SCRIPT_PATH
echo $https_proxy

if ! [[ $https_proxy == "" ]]; then
    pip install --proxy=$https_proxy --upgrade pip==9.0.3
    pip install --proxy=$https_proxy  -U -r requirements.txt
else
    pip install --upgrade pip==9.0.3
    pip install -U -r ./requirements.txt
fi

# First build the individual cron scripts
pyinstaller ./specs/xr.spec
pyinstaller ./specs/admin.spec
pyinstaller ./specs/host.spec
pyinstaller ./specs/collector.spec

# Now build the higher level binary

pyinstaller ./specs/auditor.spec
