#
# Copyright (C) 2008 bpeck@redhat.com
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

from turbogears.database import session
from turbogears import controllers, expose, flash, widgets, validate, error_handler, validators, redirect, paginate
from turbogears import identity, redirect
from cherrypy import request, response
from kid import Element
from beaker.server.widgets import myPaginateDataGrid
from beaker.server.xmlrpccontroller import RPCRoot
from beaker.server.helpers import *
from beaker.server.recipetasks import RecipeTasks
from socket import gethostname
import exceptions
import time

import cherrypy

from model import *
import string

import logging
log = logging.getLogger(__name__)

class Recipes(RPCRoot):
    # For XMLRPC methods in this class.
    exposed = True

    tasks = RecipeTasks()

    @cherrypy.expose
    @identity.require(identity.not_anonymous())
    def upload_console(self, recipe_id, data):
        """
        upload the console log in pieces 
        """
        raise NotImplementedError

    @cherrypy.expose
    @identity.require(identity.not_anonymous())
    def Abort(self, recipe_id, msg):
        """
        Set recipe status to Aborted
        """
        try:
            recipe = Recipe.by_id(recipe_id)
        except InvalidRequestError:
            raise BX(_('Invalid recipe ID: %s' % recipe_id))
        return recipe.Abort(msg)

    @cherrypy.expose
    @identity.require(identity.not_anonymous())
    def Cancel(self, recipe_id, msg):
        """
        Set recipe status to Cancelled
        """
        try:
            recipe = Recipe.by_id(recipe_id)
        except InvalidRequestError:
            raise BX(_('Invalid recipe ID: %s' % recipe_id))
        return recipe.Cancel(msg)

    @cherrypy.expose
    def system_xml(self, system_name=None):
        """ 
            Pass in system name and you'll get the active recipe
               for that system.
        """
        if not system_name:
            raise BX(_("Missing system name!"))
        try:
            system = System.by_fqdn(system_name,identity.current.user)
        except InvalidRequestError:
            raise BX(_("Invalid system %s" % system_name))
        try:
            recipexml = Watchdog.by_system(system).recipe.to_xml().toprettyxml()
        except InvalidRequestError:
            raise BX(_("No active recipe for %s" % system_name))
        return recipexml

    @cherrypy.expose
    def to_xml(self, recipe_id=None):
        """ 
            Pass in recipe id and you'll get that recipe's xml
        """
        if not recipe_id:
            raise BX(_("No recipe id provided!"))
        try:
           recipexml = Recipe.by_id(recipe_id).to_xml().toprettyxml()
        except InvalidRequestError:
            raise BX(_("Invalid Recipe ID %s" % recipe_id))
        return xml

    @expose(template='beaker.server.templates.grid')
    @paginate('list',default_order='-id')
    def index(self, *args, **kw):
        recipes = session.query(MachineRecipe)
        recipes_grid = myPaginateDataGrid(fields=[
		     widgets.PaginateDataGrid.Column(name='id', getter=lambda x:x.id, title='ID', options=dict(sortable=True)),
		     widgets.PaginateDataGrid.Column(name='whiteboard', getter=lambda x:x.whiteboard, title='Whiteboard', options=dict(sortable=True)),
		     widgets.PaginateDataGrid.Column(name='arch', getter=lambda x:x.arch, title='Arch', options=dict(sortable=True)),
		     widgets.PaginateDataGrid.Column(name='system', getter=lambda x: make_system_link(x.system), title='System', options=dict(sortable=True)),
		     widgets.PaginateDataGrid.Column(name='distro', getter=lambda x: make_distro_link(x.distro), title='Distro', options=dict(sortable=True)),
		     widgets.PaginateDataGrid.Column(name='progress', getter=lambda x: make_progress_bar(x), title='Progress', options=dict(sortable=False)),
		     widgets.PaginateDataGrid.Column(name='status.status', getter=lambda x:x.status, title='Status', options=dict(sortable=True)),
		     widgets.PaginateDataGrid.Column(name='result.result', getter=lambda x:x.result, title='Result', options=dict(sortable=True)),
                    ])
        return dict(title="Recipes", grid=recipes_grid, list=recipes, search_bar=None)