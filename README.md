# SKEO Opencart-Lazada-Shopee Extension Accessory


## Setup

Configure `config.ini` and fill up the sections for Lazada, Opencart and Shopee.

## Exec

1. Install virtualenv, pip and python2
2. Setup in terminal:

```
$ ENVS=/home/<USER>/envs
$ virtualenv -p /usr/bin/python2 ENVS/oclz
$ source $ENVS/oclz/bin/activate
$ pip install requests
```

3. Try executing:

```
$ python sync.py --chkconfig
```
