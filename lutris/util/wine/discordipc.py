"""Winestreamproxy helper module"""

__all__ = ('Winestreamproxy',)

import functools
import io
import json
import os.path
import re
import stat
import sys
import tarfile
import tempfile
import time
import traceback

import lutris.util.http
from lutris.settings import RUNTIME_DIR
from lutris.util.log import logger
from lutris.util.system import reverse_expanduser, remove_folder

_CACHE_ONE = functools.lru_cache(maxsize=1)


class WinestreamproxyPaths:
    __init__ = None
    __new__ = None

    @staticmethod
    @_CACHE_ONE
    def runtime_subdir():
        return os.path.join(RUNTIME_DIR, 'winestreamproxy')

    @classmethod
    @_CACHE_ONE
    def latest_release_json_path(cls):
        return os.path.join(cls.runtime_subdir(), 'latest.json')

    @classmethod
    @_CACHE_ONE
    def latest_release_path(cls):
        return os.path.join(cls.runtime_subdir(), 'latest')

    @classmethod
    @_CACHE_ONE
    def exe_path(cls):
        return os.path.join(cls.runtime_subdir(), 'latest', 'winestreamproxy.exe.so')


class WinestreamproxyUrls:
    __init__ = None
    __new__ = None

    _RELEASES_URL = 'https://api.github.com/repos/openglfreak/winestreamproxy/releases'

    @classmethod
    @_CACHE_ONE
    def releases_url(cls):
        return cls._RELEASES_URL

    @classmethod
    @_CACHE_ONE
    def latest_release_url(cls):
        return cls.releases_url() + '/latest'


class WinestreamproxyUtils:
    @classmethod
    def safe_write_file(cls, path, content):
        logger.debug('Writing file %s', reverse_expanduser(path))

        temp_fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(path), prefix='.' + os.path.basename(path))
        unlink = True
        try:
            with open(temp_fd, 'wb') as file:
                file.write(content)
                os.chmod(temp_fd,
                    stat.S_IRUSR
                    | stat.S_IWUSR
                    | stat.S_IRGRP
                    | stat.S_IROTH)
                os.rename(temp_path, path)
                unlink = False
        finally:
            if unlink:
                os.unlink(temp_path)

    @classmethod
    def download_and_extract_tar_file(cls, url, extract_to):
        logger.debug('Downloading and extracting %s to %s', url, reverse_expanduser(extract_to))

        temp_dir = tempfile.mkdtemp(dir=os.path.dirname(extract_to), prefix='.' + os.path.basename(extract_to))
        rmtree = True
        try:
            with io.BytesIO(lutris.util.http.Request(url).get().content) as file:
                with tarfile.open(fileobj=file) as tar:
                    tar.extractall(temp_dir)
                    os.chmod(temp_dir,
                        stat.S_IRUSR
                        | stat.S_IWUSR
                        | stat.S_IXUSR
                        | stat.S_IRGRP
                        | stat.S_IXGRP
                        | stat.S_IROTH
                        | stat.S_IXOTH)
                    os.rename(temp_dir, extract_to)
                    rmtree = False
        finally:
            if rmtree:
                remove_folder(temp_dir)

    @staticmethod
    def try_readlink(path):
        try:
            dest = os.readlink(path)
            if not os.path.isabs(dest):
                dest = os.path.join(os.path.dirname(path), dest)
            return dest
        except FileNotFoundError:
            return None

    @staticmethod
    def remove_if_exists(path):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


class Winestreamproxy:
    __init__ = None
    __new__ = None

    _CACHE_TIME = 86400
    _ASSET_NAME_REGEX = re.compile(r'^winestreamproxy-.*\.x86_64\.tar(?:\.[^\.]+)?$')

    @classmethod
    def _get_download_url_from_json(cls, data):
        for asset in data['assets']:
            if cls._ASSET_NAME_REGEX.fullmatch(asset['name']):
                return asset['browser_download_url']
        raise ValueError('Could not find download url in release info')

    @classmethod
    def _validate_release_info(cls, data):
        '''Validates the json info returned by GitHub for a release.'''
        logger.debug('Validating downloaded winestreamproxy release info')
        _ = data['tag_name']
        cls._get_download_url_from_json(data)

    @classmethod
    def _download_latest_release_json(cls):
        local_path = WinestreamproxyPaths.latest_release_json_path()
        try:
            with open(local_path, 'r') as file:
                if abs(time.time() - os.fstat(file.fileno()).st_mtime) < cls._CACHE_TIME:
                    data = json.load(file)
                    logger.info('Using cached winestreamproxy release info')
                    return data
        except FileNotFoundError:
            traceback.print_exc()
        except OSError:
            pass

        logger.info('Downloading the latest winestreamproxy release info')
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        request = lutris.util.http.Request(WinestreamproxyUrls.latest_release_url())
        try:
            request.get()
            data = cls._validate_release_info(request.json)
            WinestreamproxyUtils.safe_write_file(local_path, request.content)
            return data
        except Exception as ex:
            exc_info = sys.exc_info()
            exception = ex

        logger.error('Download failed, using cached release info')
        try:
            with open(local_path, 'r') as file:
                traceback.print_exception(*exc_info)
                return json.load(file)
        except FileNotFoundError:
            raise exception
        except OSError:
            traceback.print_exc()
            raise exception

    @classmethod
    def download(cls):
        latest_release_info = json.loads(cls._download_latest_release_json())
        tag_name = latest_release_info['tag_name']
        latest_release_path = WinestreamproxyPaths.latest_release_path()
        extract_to = os.path.join(os.path.dirname(latest_release_path), 'extracted.' + tag_name)

        if not os.path.exists(extract_to):
            logger.info('Downloading the latest winestreamproxy release')
            download_url = cls._get_download_url_from_json(latest_release_info)
            os.makedirs(os.path.dirname(latest_release_path), exist_ok=True)
            WinestreamproxyUtils.download_and_extract_tar_file(download_url, extract_to)

        old_dir = WinestreamproxyUtils.try_readlink(latest_release_path)
        if old_dir == extract_to:
            return
        if old_dir:
            old_dir_realpath = os.path.realpath(old_dir)

        WinestreamproxyUtils.remove_if_exists(latest_release_path + '.' + tag_name)
        os.symlink(extract_to, latest_release_path + '.' + tag_name, target_is_directory=False)
        os.rename(latest_release_path + '.' + tag_name, latest_release_path)

        if (old_dir and not os.path.samefile(old_dir_realpath, extract_to)
                and os.path.samefile(os.path.dirname(old_dir_realpath), WinestreamproxyPaths.runtime_subdir())
                and os.path.basename(old_dir_realpath).startswith('extracted.')):
            try:
                remove_folder(old_dir_realpath)
            except Exception:
                traceback.print_exc()

    @staticmethod
    @_CACHE_ONE
    def get_wrapper_path():
        return os.path.join(WinestreamproxyPaths.latest_release_path(), 'wrapper.sh')

    @staticmethod
    @_CACHE_ONE
    def get_environment_variables(xdg_runtime_dir):
        return {'WINESTREAMPROXY_PIPE_NAME': 'discord-ipc-0',
                'WINESTREAMPROXY_SOCKET_PATH': os.path.join(xdg_runtime_dir, 'discord-ipc-0'),
                'WINESTREAMPROXY_SYSTEM': 'true'}
