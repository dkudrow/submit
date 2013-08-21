#!/usr/bin/env python
import amqp_worker
import errno
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
INPUT_PATH = 'inputs'
RESULTS_PATH = 'results'
EXECUTION_FILES_PATH = 'execution_files'
SYNC_FILE = 'sync_files'

MAX_FILE_SIZE = 81920


class SubmissionHandler(object):
    @staticmethod
    def _cleanup():
        for filename in os.listdir('.'):
            if os.path.isdir(filename):
                shutil.rmtree(filename)
            else:
                os.unlink(filename)

    @staticmethod
    def _file_wait(filename, expected_message):
        start = time.time()
        while True:
            if os.path.isfile(filename):
                if open(filename).read() != expected_message:
                    raise Exception('Unexpected `done` file.')
                print('\t\tfile_wait took {0} seconds'
                      .format(time.time() - start))
                return
            time.sleep(0.1)

    @staticmethod
    def execute(command, stderr=None, stdin=None, stdout=None, time_limit=2,
                files=None, save=None):
        if not stderr:
            stderr = open('/dev/null', 'w')
        if not stdout:
            stdout = open('/dev/null', 'w')

        # Create temporary directory and copy execution files
        tmp_dir = tempfile.mkdtemp()
        for filename in os.listdir(EXECUTION_FILES_PATH):
            shutil.copy(os.path.join(EXECUTION_FILES_PATH, filename),
                        os.path.join(tmp_dir, filename))

        args = command.split()
        # allow some programs
        if args[0] not in ('bash', 'python', 'python2', 'python3', 'sh',
                           'valgrind'):
            args[0] = os.path.join(os.getcwd(), SRC_PATH, args[0])
            if not os.path.isfile(args[0]):
                raise NonexistentExecutable()
        else:
            # Need to copy the script(s) if they are listed on the command line
            for arg in args:
                src = os.path.join(SRC_PATH, arg)
                if os.path.isfile(src):
                    shutil.copy(src, os.path.join(tmp_dir, arg))

        # Hacks to give more time to some scripts:
        if args[0] in ('valgrind',):
            time_limit = 4
        elif len(args) > 2 and args[1] == 'turtle_capture.sh':
            time_limit = 16  # How can we run this faster?

        # Run command with a timelimit
        # TODO: Do we only get partial output with stdout?
        try:
            poll = select.epoll()
            main_pipe = Popen(args, stdin=stdin, stdout=PIPE, stderr=stderr,
                              cwd=tmp_dir, preexec_fn=os.setsid)
            poll.register(main_pipe.stdout, select.EPOLLIN | select.EPOLLHUP)
            do_poll = True
            start = time.time()
            while do_poll:
                remaining_time = start + time_limit - time.time()
                if remaining_time <= 0:
                    if main_pipe.poll() is None:  # Ensure it's still running
                        # Kill the entire process group
                        os.killpg(main_pipe.pid, signal.SIGKILL)
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
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                raise NonexistentExecutable()
            else:
                raise
        finally:
            if save:  # Attempt to copy files requiring saving
                src = os.path.join(tmp_dir, save[0])
                if os.path.isfile(src):
                    shutil.copy(src, save[1])
            shutil.rmtree(tmp_dir)

    def __init__(self, settings, is_daemon):
        settings['working_dir'] = os.path.expanduser(settings['working_dir'])
        self.worker = amqp_worker.AMQPWorker(
            settings['server'], settings['queue_tell_worker'], self.do_work,
            is_daemon=is_daemon, working_dir=settings['working_dir'],
            log_file=settings['log_file'], pid_file=settings['pid_file'])
        self.settings = settings

    def communicate(self, queue, complete_file, submission_id, testable_id):
        hostname = socket.gethostbyaddr(socket.gethostname())[0]
        username = pwd.getpwuid(os.getuid())[0]
        data = {'complete_file': complete_file, 'remote_dir': os.getcwd(),
                'user': username, 'host': hostname,
                'submission_id': submission_id, 'testable_id': testable_id}
        self.worker.channel.queue_declare(queue=queue, durable=True)
        self.worker.channel.basic_publish(
            exchange='', body=json.dumps(data), routing_key=queue,
            properties=pika.BasicProperties(delivery_mode=2))
        self._file_wait(complete_file,
                        '{0}.{1}'.format(submission_id, testable_id))

    def do_work(self, submission_id, testable_id):
        self._cleanup()
        print('Got job: {0}.{1}'.format(submission_id, testable_id))
        # sync_files worker will verify the request using this file
        with open('sync_verification', 'w') as fp:
            fp.write('{0}.{1}'.format(submission_id, testable_id))
        self.communicate(queue=self.settings['queue_sync_files'],
                         complete_file=SYNC_FILE,
                         submission_id=submission_id, testable_id=testable_id)
        print('\tFiles synced: {0}.{1}'.format(submission_id, testable_id))
        data = json.load(open('post_sync_data'))
        os.mkdir(RESULTS_PATH)
        if self.make_project(data['executable'], data['make_target']):
            self.run_tests(data['test_cases'])
        # Move SYNC_FILE for fetch_result verification worker
        os.rename(SYNC_FILE, os.path.join(RESULTS_PATH, SYNC_FILE))
        self.communicate(queue=self.settings['queue_fetch_results'],
                         complete_file='results_fetched',
                         submission_id=submission_id, testable_id=testable_id)
        print('\tResults fetched: {0}.{1}'.format(submission_id, testable_id))

    def make_project(self, executable, make_target):
        """Build the project and return True if the executable exists."""
        with open(os.path.join(RESULTS_PATH, 'make'), 'w') as fp:
            if make_target:
                command = 'make -f ../Makefile -C {0} {1}'.format(
                    SRC_PATH, make_target)
                pipe = Popen(command, shell=True, stdout=fp, stderr=STDOUT)
                pipe.wait()
                if pipe.returncode != 0:
                    return False
            if not os.path.isfile(os.path.join(SRC_PATH, executable)):
                fp.write('Expected executable `{0}` does not exist\n'
                         .format(executable))
                return False
            return True

    def run_tests(self, test_cases):
        def execute(*args, **kwargs):
            try:
                result['extra'] = self.execute(*args, **kwargs)
                result['status'] = 'success'
            except NonexistentExecutable:
                result['status'] = 'nonexistent_executable'
            except SignalException as exc:
                result['extra'] = exc.signum
                result['status'] = 'signal'
            except TimeoutException:
                result['status'] = 'timed_out'

        results = {}
        for tc in test_cases:
            output_file = os.path.join(RESULTS_PATH, 'tc_{0}'.format(tc['id']))
            if tc['stdin']:
                stdin_file = os.path.join(INPUT_PATH, tc['stdin'])
                stdin = open(stdin_file)
            else:
                stdin = None
            result = {'extra': None}

            # Mange output file
            if tc['source'] != 'file':
                with open(output_file, 'wb') as output:
                    if tc['source'] == 'stdout':
                        stdout = output
                        stderr = None
                    else:
                        stdout = None
                        stderr = output
                    execute(tc['args'], stderr=stderr, stdin=stdin,
                            stdout=stdout)
                max_file_size = MAX_FILE_SIZE
            else:
                execute(tc['args'], save=(tc['output_filename'], output_file))
                if tc['output_filename'].endswith('.png'):
                    max_file_size = 131072  # Avoid truncating images

            if not os.path.isfile(output_file):
                # Hack on this status until we update the ENUM
                if result['status'] == 'success':
                    # Don't overwrite other statuses
                    result['status'] = 'output_limit_exceeded'
            elif os.path.getsize(output_file) > max_file_size:
                # Truncate output file size
                print('Truncating outputfile', os.path.getsize(output_file))
                fd = os.open(output_file, os.O_WRONLY)
                os.ftruncate(fd, max_file_size)
                os.close(fd)
                if result['status'] == 'success':
                    # Don't overwrite other statuses
                    result['status'] = 'output_limit_exceeded'
            results[tc['id']] = result
        with open(os.path.join(RESULTS_PATH, 'test_cases'), 'w') as fp:
            json.dump(results, fp)


class NonexistentExecutable(Exception):
    """Indicate that the expected binary does not exist."""


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
