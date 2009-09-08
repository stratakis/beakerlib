# Beah - Test harness. Part of Beaker project.
#
# Copyright (C) 2009 Marian Csontos <mcsontos@redhat.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

from twisted.web.xmlrpc import Proxy
from twisted.internet import reactor

import os, exceptions, tempfile, pprint
from xml.etree import ElementTree
from beah.core.backends import ExtBackend
from beah.core import command
from beah.core.constants import ECHO, RC
import simplejson as json

#HOST='beaker-01.app.eng.bos.redhat.com'
HOST='localhost:5222'
PATH='client'
#XMLRPC_URL='https://%s/%s' % (HOST, PATH)
XMLRPC_URL='http://%s/%s' % (HOST, PATH)

#  recipes.to_xml(recipe_id)
#  recipes.system_xml(fqdn)
#  parse XML :-(
#  recipes.tasks.Start(task_id, kill_time)
#  recipes.tasks.Result(task_id, result_type, path, score, summary)
#  - result_type: Pass|Warn|Fail|Panic
#  recipes.tasks.Stop(task_id, stop_type, msg)
#  - stop_type: Stop|Abort|Cancel

def parse_recipe_xml(input_xml):
    er = ElementTree.fromstring(input_xml)
    task_env = {}

    rs = er.get('status')
    # FIXME: is this condition correct?
    if rs != 'Running' and True:
        print "This recipe has finished."
        return None

    task_env.update(
            RECIPEID=er.get('id'),
            JOBID=er.get('job_id'),
            RECIPESETID=er.get('recipe_set_id'),
            HOSTNAME=er.get('system'))

    for task in er.findall('task'):
        ts = task.get('status')

        # FIXME: is this condition correct?
        #if ts == 'Running':
        #    break
        if ts != 'Waiting' and ts != 'Running':
            continue

        if ts == 'Running':
            # FIXME: A task SHOULD BE already running.
            return None

        task_env.update(
                TASKID=task.get('id'),
                TASKNAME=task.get('name'),
                ROLE=task.get('role'))

        # FIXME: Anything else to save?

        for p in task.getiterator('param'):
            task_env[p.get('name')]=p.get('value')

        for r in task.getiterator('role'):
            role = []
            for s in r.findall('system'):
                role.append(s.get('value'))
            task_env[r.get('value')]=' '.join(role)

        ewd = task.get('avg_time')
        rpm = task.find('rpm').get('name')

        return dict(task_env=task_env, rpm=rpm, ewd=ewd)

    return None

import beah.system
# FIXME: using rpm's, yum - too much Fedora centric(?)
from beah.system.dist_fedora import RPMInstaller
def mk_beaker_task(rpm):
    # FIXME: see rhts-test-runner for ideas:
    # /home/mcsontos/rhts/rhts/test-env-lab/bin/rhts-test-runner.sh

    # create a script to: check, install and run a test
    # should task have an "envelope" - e.g. binary to run...

    # repositories: http://rhts.redhat.com/rpms/{development,production}/noarch/
    # see scratch.tmp/rhts-tests.repo

    # have a look at:
    # http://intranet.corp.redhat.com/ic/intranet/RHTSMainPage.html#devel
    e = RPMInstaller(rpm)
    e.make()
    return e.executable

class BeakerLCBackend(ExtBackend):

    def on_idle(self):
        #self.recipe_id = int(os.getenv('RECIPEID'))
        #self.proxy.callRemote('recipes.to_xml',
        #        self.recipe_id).addCallback(self.handle_new_task)
        self.proxy.callRemote('recipes.system_xml',
                os.getenv('HOSTNAME')).addCallback(self.handle_new_task)

    def set_controller(self, controller=None):
        ExtBackend.set_controller(self, controller)
        if controller:
            self.proxy = Proxy(XMLRPC_URL)
            self.on_idle()

    def handle_new_task(self, result):
        pprint.pprint(result)
        if not result or not result.has_key('xml') or not result['xml']:
            print "* Nothing to do..."
            reactor.callLater(60, self.on_idle)
            return

        self.recipe_xml = result['xml']

        self.task_data = parse_recipe_xml(self.recipe_xml)
        pprint.pprint(self.task_data)

        if self.task_data is None:
            print "* Recipe done. Nothing to do..."
            reactor.callLater(60, self.on_idle)
            return

        self.executable = mk_beaker_task(self.task_data['rpm'])

        self.controller.proc_cmd(self, command.run(self.executable,
                env=self.task_data['task_env'],
                args=[self.task_data['rpm']]))

        # Persistent env (handled by Controller?) - env to run task under,
        # task can change it, and when restarted will continue with same
        # env(?) Task is able to handle this itself. Provide a library...

    def pre_proc(self, evt):
        # FIXME: remove
        pprint.pprint(evt)

    @staticmethod
    def stop_type(rc):
        return "Stop" if rc==0 else "Cancel"

    def mk_msg(self, **kwargs):
        return json.dumps(kwargs)

    def proc_evt_echo(self, evt):
        if (evt.arg('cmd').command()=='run'):
            rc = echo.arg('rc')
            if rc!=ECHO.OK:
                # FIXME: Start was not issued. Is it OK?
                self.proxy.callRemote('recipes.tasks.Stop',
                        int(self.task_data['task_env']['TASKID']),
                        self.stop_type("Cancel"),
                        self.mk_msg(reason="Harness could not run the task.", event=evt)).addCallback(self.handle_Stop)

    def proc_evt_start(self, evt):
        self.proxy.callRemote('recipes.tasks.Start',
                int(self.task_data['task_env']['TASKID']),
                0)
        # FIXME: start local watchdog

    def proc_evt_end(self, evt):
        self.proxy.callRemote('recipes.tasks.Stop',
                int(self.task_data['task_env']['TASKID']),
                self.stop_type(evt.arg("rc",None)),
                self.mk_msg(event=evt)).addCallback(self.handle_Stop)

    def handle_Stop(self, result):
        self.on_idle()

    def close(self):
        # FIXME: send a bye to server? (Should this be considerred an abort?)
        reactor.callLater(1, reactor.stop)

def main():
    from beah.wires.internals.twbackend import start_backend
    backend = BeakerLCBackend()
    # Start a default TCP client:
    start_backend(backend, byef=lambda evt: reactor.callLater(1, reactor.stop))

if __name__ == '__main__':
    from twisted.internet import reactor
    print main.__doc__
    #os.environ['RECIPEID'] = '21'
    main()
    reactor.run()
