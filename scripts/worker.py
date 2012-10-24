#!/usr/bin/env python
import ConfigParser
import amqp_worker
import json
import os
import pika
import pwd
import shutil
import select
import signal
import socket
import sys
import tempfile
import time
from subprocess import Popen, PIPE, STDOUT


SRC_PATH = 'src'
INPUT_PATH = 'input'
RESULTS_PATH = 'results'


class SubmissionHandler(object):
    @staticmethod
    def _cleanup():
        for filename in os.listdir('.'):
            if os.path.isdir(filename):
                shutil.rmtree(filename)
            else:
                os.unlink(filename)

    @staticmethod
    def _file_wait(filename, submission_id):
        start = time.time()
        while True:
            if os.path.isfile(filename):
                if open(filename).read() != str(submission_id):
                    raise Exception('Found wrong submission')
                print('file_wait took {0} seconds'.format(time.time() - start))
                return
            time.sleep(1)

    @staticmethod
    def execute(command, stdout, stdin=None, time_limit=2.9999999, files=None,
                capture_stderr=False):
        if not capture_stderr:
            stderr = open('/dev/null', 'w')
        else:
            stderr = STDOUT

        # Prefix path to command
        command = os.path.join(os.getcwd(), SRC_PATH, command)

        # Run command with a timelimit
        tmp_dir = tempfile.mkdtemp()
        try:
            poll = select.epoll()
            main_pipe = Popen(command.split(), stdin=stdin, stdout=PIPE,
                              stderr=stderr, cwd=tmp_dir)
            poll.register(main_pipe.stdout, select.EPOLLIN | select.EPOLLHUP)
            do_poll = True
            start = time.time()
            while do_poll:
                remaining_time = start + time_limit - time.time()
                if remaining_time <= 0:
                    if main_pipe.poll() is None:  # Ensure it's still running
                        os.kill(main_pipe.pid, signal.SIGKILL)
                        raise TimeoutException()
                for file_descriptor, event in poll.poll(remaining_time):
                    stdout.write(os.read(file_descriptor, 8192))
                    if event == select.POLLHUP:
                        poll.unregister(file_descriptor)
                        do_poll = False
            main_status = main_pipe.wait()
            if main_status < 0:
                raise SignalException(-1 * main_status)
            return main_status
        finally:
            shutil.rmtree(tmp_dir)

    def __init__(self, settings, is_daemon):
        settings['working_dir'] = os.path.expanduser(settings['working_dir'])
        self.worker = amqp_worker.AMQPWorker(
            settings['server'], settings['queue_tell_worker'], self.do_work,
            is_daemon=is_daemon, working_dir=settings['working_dir'])
        self.settings = settings

    def communicate(self, queue, complete_file, submission_id):
        hostname = socket.gethostbyaddr(socket.gethostname())[0]
        username = pwd.getpwuid(os.getuid())[0]
        data = {'complete_file': complete_file, 'remote_dir': os.getcwd(),
                'user': username, 'host': hostname,
                'submission_id': submission_id}
        self.worker.channel.queue_declare(queue=queue, durable=True)
        self.worker.channel.basic_publish(
            exchange='', body=json.dumps(data), routing_key=queue,
            properties=pika.BasicProperties(delivery_mode=2))
        self._file_wait(complete_file, submission_id)

    def do_work(self, submission_id):
        self._cleanup()
        print('Got job: {0}'.format(submission_id))
        self.communicate(queue=self.settings['queue_sync_files'],
                         complete_file='sync_files',
                         submission_id=submission_id)
        print('Files synced: {0}'.format(submission_id))
        os.mkdir(RESULTS_PATH)
        if self.make_project():
            self.run_tests()
        self.communicate(queue=self.settings['queue_fetch_results'],
                         complete_file='results_fetched',
                         submission_id=submission_id)
        print('Results fetched: {0}'.format(submission_id))

    def make_project(self):
        if not os.path.isfile('Makefile'):
            return True
        command = 'make -f ../Makefile -C {}'.format(SRC_PATH)
        with open(os.path.join(RESULTS_PATH, 'make'), 'w') as fp:
            pipe = Popen(command, shell=True, stdout=fp, stderr=STDOUT)
            pipe.wait()
        return pipe.returncode == 0

    def run_tests(self):
        if not os.path.isfile('test_cases'):
            return
        test_cases = json.load(open('test_cases'))
        results = {}
        for tc in test_cases:
            output_file = os.path.join(RESULTS_PATH, 'tc_{}'.format(tc['id']))
            result = {'signal': None, 'status': None, 'timed_out': False}
            with open(output_file, 'wb') as fd:
                try:
                    result['status'] = self.execute(tc['args'], stdout=fd)
                except SignalException as exc:
                    result['signal'] = exc.signum
                except TimeoutException:
                    result['timed_out'] = True
            results[tc['id']] = result
        with open(os.path.join(RESULTS_PATH, 'test_cases'), 'w') as fp:
            json.dump(results, fp)


class SignalException(Exception):
    """Indicate that a process was terminated via a signal"""
    def __init__(self, signum):
        self.signum = signum


class TimeoutException(Exception):
    """Indicate that a process's execution timed out."""


def main():
    parser = amqp_worker.base_argument_parser()
    args, settings = amqp_worker.parse_base_args(parser, 'worker')
    handler = SubmissionHandler(settings, args.daemon)
    handler.worker.start()


if __name__ == '__main__':
    sys.exit(main())
