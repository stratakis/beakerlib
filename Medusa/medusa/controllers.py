from turbogears.database import session
from turbogears import controllers, expose, flash, widgets, validate, error_handler, validators, redirect, paginate
from model import *
from turbogears import identity, redirect
from medusa.power import PowerTypes, PowerControllers
from medusa.group import Groups
from medusa.labcontroller import LabControllers
from medusa.distro import Distros
from medusa.widgets import myPaginateDataGrid
from medusa.widgets import Power
from medusa.widgets import SearchBar, SystemForm, SystemGroups
from medusa.xmlrpccontroller import RPCRoot
from cherrypy import request, response
from tg_expanding_form_widget.tg_expanding_form_widget import ExpandingForm

from kid import Element
import cherrypy
import md5

# for debugging
import sys

# from medusa import json
# import logging
# log = logging.getLogger("medusa.controllers")
import breadcrumbs
from datetime import datetime

def make_link(url, text):
    # make an <a> element
    a = Element('a', {'class': 'list'}, href=url)
    a.text = text
    return a

#def search():
#    """Return proper join for search"""
#    tables = dict ( Cpu = 'Cpu.q.system == System.q.id' 
#    tables = dict ( Cpu = (Cpu.q.system == System.q.id))

#    systems = System.select(AND(*your_dict.iter_values()))  ?

class Users:

    @expose(format='json')
    def by_name(self, input):
        input = input.lower()
        return dict(matches=User.list_by_name(input))

class Devices:

    @expose(template='medusa.templates.grid')
    @paginate('list')
    def view(self, id):
        device = session.query(Device).get(id)
        systems = System.all(identity.current.user).join('devices').filter_by(id=id)
        device_grid = myPaginateDataGrid(fields=[
                        ('System', lambda x: make_link("/view/%s" % x.fqdn, x.fqdn)),
                        ('Description', lambda x: device.description),
                       ])
        return dict(title="", grid = device_grid, search_bar=None,
                                              list = systems)

    @expose(template='medusa.templates.grid')
    @paginate('list',default_order='description',limit=50,allow_limit_override=True)
    def default(self, *args, **kw):
        args = list(args)
        if len(args) == 1:
            devices = session.query(Device).join('device_class').filter_by(device_class=args[0])
                
        if len(args) != 1:
            devices = session.query(Device).join('device_class')
        devices_grid = myPaginateDataGrid(fields=[
                        widgets.PaginateDataGrid.Column(name='description', getter=lambda x: make_link("/devices/view/%s" % x.id, x.description), title='Description', options=dict(sortable=True)),
                        widgets.PaginateDataGrid.Column(name='device_class.device_class', getter=lambda x: x.device_class, title='Type', options=dict(sortable=True)),
                        widgets.PaginateDataGrid.Column(name='bus', getter=lambda x: x.bus, title='Bus', options=dict(sortable=True)),
                        widgets.PaginateDataGrid.Column(name='driver', getter=lambda x: x.driver, title='Driver', options=dict(sortable=True)),
                        widgets.PaginateDataGrid.Column(name='vendor_id', getter=lambda x: x.vendor_id, title='Vendor ID', options=dict(sortable=True)),
                        widgets.PaginateDataGrid.Column(name='device_id', getter=lambda x: x.device_id, title='Device ID', options=dict(sortable=True)),
                        widgets.PaginateDataGrid.Column(name='subsys_vendor_id', getter=lambda x: x.subsys_vendor_id, title='Subsys Vendor ID', options=dict(sortable=True)),
                        widgets.PaginateDataGrid.Column(name='subsys_device_id', getter=lambda x: x.subsys_device_id, title='Subsys Device ID', options=dict(sortable=True)),
                       ])
        return dict(title="Devices", grid = devices_grid, search_bar=None,
                                     list = devices)

class Root(RPCRoot):
    powertypes = PowerTypes()
    powercontrollers = PowerControllers()
    devices = Devices()
    groups = Groups()
    labcontrollers = LabControllers()
    distros = Distros()
    users = Users()

    id         = widgets.HiddenField(name='id')
    submit     = widgets.SubmitButton(name='submit')

    autoUsers  = widgets.AutoCompleteField(name='user',
                                           search_controller="/users/by_name",
                                           search_param="input",
                                           result_name="matches")
    

    owner_form    = widgets.TableForm(
        'Owner',
        fields = [id, autoUsers,],
        action = 'save_data',
        submit_text = _(u'Change'),
    )

    search_bar = SearchBar(name='systemsearch',
                           label=_(u'System Search'),
                           table_callback=System.get_tables,
                           search_controller='/get_fields'
                 )
    power = Power(name='powercontrol',
                 label=_(u'Power Control'),
                 callback=powercontrollers.get_powercontrollers,
                 search_controller='/powercontrollers/get_power_args',
                 system_id='system_id' # This is Ugly. :(
                 # Should be able to get rid of this 
            )

    system_form = SystemForm()

    @expose(format='json')
    def get_fields(self, table_name):
        return dict( fields = System.get_fields(table_name))

    @expose(template='medusa.templates.grid')
    @paginate('list',default_order='fqdn')
    def index(self, *args, **kw):
        return self.systems(systems = System.all(identity.current.user), *args, **kw)

    @expose(template='medusa.templates.grid')
    @paginate('list',default_order='fqdn')
    def available(self, *args, **kw):
        return self.systems(systems = System.available(identity.current.user), *args, **kw)

    @expose(template='medusa.templates.grid')
    @paginate('list',default_order='fqdn')
    def mine(self, *args, **kw):
        return self.systems(systems = System.mine(identity.current.user), *args, **kw)

    # @identity.require(identity.in_group("admin"))
    def systems(self, systems, *args, **kw):
        if kw.get("systemsearch"):
            searchvalue = kw['systemsearch']
            for search in kw['systemsearch']:
                clsinfo = System.get_dict()[search['table']]
                cls = clsinfo['cls']
                col = getattr(cls,search['column'], None)
                systems = systems.join(clsinfo['joins'])
                if search['operation'] == 'greater than':
                    systems = systems.filter(col>search['value'])
                if search['operation'] == 'less than':
                    systems = systems.filter(col<search['value'])
                if search['operation'] == 'not equal':
                    systems = systems.filter(col!=search['value'])
                if search['operation'] == 'equal':
                    systems = systems.filter(col==search['value'])
                if search['operation'] == 'like':
                    value = '%%%s%%' % search['value']
                    systems = systems.filter(col.like(value))
        else:
            searchvalue = None
        systems_grid = myPaginateDataGrid(fields=[
                        widgets.PaginateDataGrid.Column(name='fqdn', getter=lambda x: make_link("/view/%s" % x.fqdn, x.fqdn), title='System', options=dict(sortable=True)),
                        widgets.PaginateDataGrid.Column(name='status.status', getter=lambda x: x.status, title='Status', options=dict(sortable=True)),
                        widgets.PaginateDataGrid.Column(name='vendor', getter=lambda x: x.vendor, title='Vendor', options=dict(sortable=True)),
                        widgets.PaginateDataGrid.Column(name='model', getter=lambda x: x.model, title='Model', options=dict(sortable=True)),
                        widgets.PaginateDataGrid.Column(name='location', getter=lambda x: x.location, title='Location', options=dict(sortable=True)),
                        widgets.PaginateDataGrid.Column(name='type.type', getter=lambda x: x.type, title='Type', options=dict(sortable=True)),
                        widgets.PaginateDataGrid.Column(name='owner', getter=lambda x: x.owner, title='Owner', options=dict(sortable=True)),
                        widgets.PaginateDataGrid.Column(name='date_lastcheckin', getter=lambda x: x.date_lastcheckin, title='Last Checkin', options=dict(sortable=True)),
                       ])
        return dict(title="Systems", grid = systems_grid,
                                     list = systems, searchvalue = searchvalue,
                                     action = '.',
                                     options = {},
                                     search_bar = self.search_bar)

    @expose(format='json')
    def by_fqdn(self, input):
        input = input.lower()
        search = System.list_by_fqdn(input,identity.current.user).all()
        matches =  [match.fqdn for match in search]
        return dict(matches = matches)

    @expose()
    @identity.require(identity.not_anonymous())
    def group_remove(self, *args, **kw):
        removed = None
        if kw.get('system_id') and kw.get('group_id'):
            try:
                system = System.by_id(kw['system_id'],identity.current.user)
            except:
                return dict( reponse =_(u"Invalid Permision"))
        else:
            return dict( reponse = _(u"system_id and group_id must be provided"))
        if system.owner == identity.current.user \
          or identity.in_group("admin"):
           for group in system.groups:
               if group.group_id == int(kw['group_id']):
                   system.groups.remove(group)
                   removed = group
                   activity = Activity(identity.current.user.user_id, 'system', kw['id'], 'group', group.group_id, "")
	           session.save_or_update(activity)
        if removed:
            return dict( reponse = _(u"%s Removed" % removed.display_name))
        else:
            return dict( reponse = _(u"Group ID not found"))

    @expose()
    @identity.require(identity.not_anonymous())
    def group_add(self, *args, **kw):
        group = None
        if kw.get('id') and kw.get('group'):
            try:
                system = System.by_id(kw['id'],identity.current.user)
            except:
                return dict( reponse =_(u"Invalid Permision"))
        else:
            return dict( reponse = _(u"system_id and group_id must be provided"))
        if system.owner == identity.current.user \
          or identity.in_group("admin"):
            group = Group.by_name(kw['group']['text'])
            system.groups.append(group)
            activity = Activity(identity.current.user.user_id, 'system', kw['id'], 'group', "", group.group_id)
	    session.save_or_update(activity)
        return dict( response = _(u"%s Added" % group.display_name))

    @expose(format='json')
    def ajax_grid_group(self, system_id):
        system = System.query().filter(System.id == int(system_id)).one()
        rows = []
        actions = {}
        if system.owner == identity.current.user \
          or identity.in_group("admin"):
            actions = {'remove':{'function':'system_group.retrieveRemove','params':[]}}
        headers = ["ID", "Name", "Display Name"]
        for group in system.groups:
            row = [group.group_id, group.group_name,group.display_name]
            rows.append(row)
        return dict(
            headers = headers,
            rows = rows,
            actions = actions,
        )

    @expose(template="medusa.templates.system")
    def view(self, fqdn=None, **kw):
        widget = widgets.Tabber()
        if fqdn:
            try:
                system = System.by_fqdn(fqdn,identity.current.user)
            except InvalidRequestError:
                flash( _(u"Unable to find %s" % fqdn) )
                redirect("/")
        elif kw.get('id'):
            try:
                system = System.by_id(kw['id'],identity.current.user)
            except InvalidRequestError:
                flash( _(u"Unable to find system with id of %s" % kw['id']) )
                redirect("/")
        else:
            system = None
        options = {}
        readonly = False
        if system:
            groupgrid = widgets.DataGrid(fields=[
                                     ('Groups', lambda x:x.display_name)
                                  ])
            title = system.fqdn
            if (system.owner == identity.current.user \
              or identity.in_group("admin")) \
              and not identity.current.anonymous:
                options['owner_change_text'] = ' (Change)'
                groupgrid.fields.append((' ', lambda x: make_link('removeGroup?system_id=%s&group_id=%s' % (system.id, x.group_id))))
            else:
                readonly = True
            if system.can_share(identity.current.user):
                options['user_change_text'] = ' (Take)'
            if system.user:
                if system.user == identity.current.user \
                  or identity.in_group("admin"):
                    options['user_change_text'] = ' (Return)'
            system_group_form = SystemGroups(
                 ajax_grid_url     = "/ajax_grid_group",
                 search_controller = "/groups/by_name",
                 removecontroller = '/group_remove',
                 search_param      = "name",
                 result_name       = "groups",
                 systemid          = system.id,
                 readonly          = readonly
            )
        else:
            system_group_form = None
            title = 'New'

        options['readonly'] = readonly
        return dict(
            title   = title,
            system  = system,
            widget  = widget,
            system_form = self.system_form,
            system_group_form = system_group_form,
            action = '/save',
            system_group_action = '/group_save',
            value = system,
            options = options,
            activity =  Activity.system(system.id),
        )
         
    new = view    

    @expose(template='medusa.templates.form')
    @identity.require(identity.not_anonymous())
    def owner_change(self, id):
        try:
            system = System.by_id(id,identity.current.user)
        except InvalidRequestError:
            flash( _(u"Unable to find system with id of %s" % id) )
            redirect("/")
        if system.owner != identity.current.user \
          and not identity.in_group('admin'):
            flash( _(u"Insufficient permissions to change owner"))
            redirect("/")

        return dict(
            title   = "Change Owner for %s" % system.fqdn,
            form = self.owner_form,
            action = '/save_owner',
            options = None,
            value = {'id': system.id},
        )
            
    @expose()
    @identity.require(identity.not_anonymous())
    def save_owner(self, id, *args, **kw):
        try:
            system = System.by_id(id,identity.current.user)
        except InvalidRequestError:
            flash( _(u"Unable to find system with id of %s" % id) )
            redirect("/")
        if system.owner != identity.current.user \
          and not identity.in_group('admin'):
            flash( _(u"Insufficient permissions to change owner"))
            redirect("/")
        user = User.by_user_name(kw['user']['text'])
        activity = Activity(identity.current.user.user_id, 'system', id, 'owner', system.owner.user_id, user.user_id)
        system.owner = user
	session.save_or_update(activity)
        flash( _(u"OK") )
        redirect("/")

    @expose()
    def user_change(self, id):
        status = None
        activity = None
        try:
            system = System.by_id(id,identity.current.user)
        except InvalidRequestError:
            flash( _(u"Unable to find system with id of %s" % id) )
            redirect("/")
        if system.user:
            if system.user == identity.current.user:
                status = "Returned"
                activity = Activity(identity.current.user.user_id, 'system', system.id, 'user', system.user.user_id, '')
                system.user = None
            else:
                activity = Activity(identity.current.user.user_id, 'system', system.id, 'user', system.user.user_id, identity.current.user.user_id)
        else:
            if system.can_share(identity.current.user):
                status = "Reserved"
                activity = Activity(identity.current.user.user_id, 'system', system.id, 'user', '', identity.current.user.user_id)
                system.user = identity.current.user
        session.save_or_update(system)
        session.save_or_update(activity)
        flash( _(u"%s %s" % (status,system.fqdn)) )
        redirect(".")

#    @error_handler(view)
    @expose()
    def save(self, **kw):
        if kw.get('id'):
            try:
                system = System.by_id(kw['id'],identity.current.user)
            except InvalidRequestError:
                flash( _(u"Unable to save %s" % kw['id']) )
                redirect("/")
            system.fqdn = kw['fqdn']
        else:
            if System.query().filter(System.fqdn == kw['fqdn']).count() != 0:   
                flash( _(u"%s already exists!" % kw['fqdn']) )
                redirect("/")
            system = System(fqdn=kw['fqdn'],owner=identity.current.user)
# TODO what happens if you log changes here but there is an issue and the actual change to the system fails?
#      would be good to have the save wait until the system is updated
# TODO log  group +/-
        # Fields missing from kw have been set to NULL
        log_fields = [ 'fqdn', 'vendor', 'lender', 'model', 'serial', 'location', 'type_id', 'checksum', 'status_id', 'lab_controller_id' ]
        for field in log_fields:
            current_val = str(system.__dict__[field])
            # catch nullable fields return None.
            if current_val == 'None':
                current_val = ""
            if kw.get(field):
                if current_val != str(kw[field]):
#                    sys.stderr.write("\nfield: " + field + ", Old: " +  current_val + ", New: " +  str(kw[field]) + " " +  "\n")
                    activity = Activity(identity.current.user.user_id, 'system', system.id, field, current_val, kw[field])
                    session.save_or_update(activity)
            else:
                 if current_val != "":
                    activity = Activity(identity.current.user.user_id, 'system', system.id, field, current_val, "")
                    session.save_or_update(activity)
        log_bool_fields = [ 'shared', 'private' ]
        for field in log_bool_fields:
            current_val = system.__dict__[field]
            if kw.get(field):
                if current_val != True:
                    activity = Activity(identity.current.user.user_id, 'system', system.id, field, current_val, "1")
                    session.save_or_update(activity)
            else:
                if current_val != False:
                    activity = Activity(identity.current.user.user_id, 'system', system.id, field, current_val, "0")
                    session.save_or_update(activity)
        system.status_id=kw['status_id']
        system.location=kw['location']
        system.model=kw['model']
        system.type_id=kw['type_id']
        system.serial=kw['serial']
        system.vendor=kw['vendor']
        system.lender=kw['lender']
        system.date_modified = datetime.utcnow()
        if kw.get('shared'):
            system.shared=kw['shared']
        else:
            system.shared=False
        if kw.get('private'):
            system.private=kw['private']
        else:
            system.private=False
        if kw['lab_controller_id'] == 0:
            system.lab_controller_id = None
        else:
            system.lab_controller_id = kw['lab_controller_id']

        session.save_or_update(system)
        flash( _(u"OK") )
        redirect(".")

    @cherrypy.expose
    def push(self, fqdn=None, inventory=None):
        if not fqdn:
            return (0,"You must supply a FQDN");
        if not inventory:
            return (0,"No inventory data provided");

        md5sum = md5.new("%s" % inventory).hexdigest()

        try:
            system = System.query.filter(System.fqdn == fqdn).one()
        except:
            # New system, add it.
            print fqdn
            system = System(fqdn=fqdn)
            # Default to first user
                                 # , model=inventory['model'],
                                 # date_modified=datetime.utcnow(),
                                 # vendor=inventory['vendor'])
            pass
        system.update(inventory)
        return 0

    @expose(template="medusa.templates.login")
    def login(self, forward_url=None, previous_url=None, *args, **kw):

        if not identity.current.anonymous \
            and identity.was_login_attempted() \
            and not identity.get_identity_errors():
            raise redirect(forward_url)

        forward_url=None
        previous_url= request.path

        if identity.was_login_attempted():
            msg=_("The credentials you supplied were not correct or "
                   "did not grant access to this resource.")
        elif identity.get_identity_errors():
            msg=_("You must provide your credentials before accessing "
                   "this resource.")
        else:
            msg=_("Please log in.")
            forward_url= request.headers.get("Referer", "/")
            
        response.status=403
        return dict(message=msg, previous_url=previous_url, logging_in=True,
                    original_parameters=request.params,
                    forward_url=forward_url)

    @expose()
    def logout(self):
        identity.current.logout()
        raise redirect("/")

    @expose(template='medusa.templates.activity')
    def activity(self, *args, **kw):
# TODO This is mainly for testing
# if it hangs around it should check for admin access
        return dict(title="Activity", search_bar=None, activity = Activity.all())

