import os
import random
import socketio
from pymongo import MongoClient
from flask import Flask, render_template
# from flask.ext.login import LoginManager, UserMixin, login_required


# set this to 'threading', 'eventlet', or 'gevent'
async_mode = 'gevent'

if async_mode == 'gevent':
    from gevent import monkey
    monkey.patch_all()

sio = socketio.Server(logger=True, async_mode=async_mode)
app = Flask(__name__)
app.wsgi_app = socketio.Middleware(sio, app.wsgi_app)
app.config['SECRET_KEY'] = 'spywithmylittleeye!'

# sio = SocketIO(app)
# login_manager = LoginManager()
# login_manager.init_app(app)

clients_waiting = {}
clients_partner = {}
questioner_anns = {}
questioner_annid = {}

client = MongoClient(os.environ['MONGODB_URL'])
db = client.coco.images


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/game')
def game():
    return render_template('game.html')


@sio.on('newquestion', namespace='/game')
def new_question(sid, message):
    sio.emit('newquestion', message,
             room=clients_partner[sid], namespace='/game')


@sio.on('new answer', namespace='/game')
def new_answer(sid, message):
    sio.emit('new answer', message,
             room=clients_partner[sid], namespace='/game')


@sio.on('guess', namespace='/game')
def guess(sid, obj):
    obj = obj.lower()
    if sid in questioner_anns:
        cat = questioner_anns[sid][questioner_annid[sid]]['category']
        if cat == obj:
            objs = []
            for x in questioner_anns[sid]:
                if x['category'] == cat:
                    objs.append(x)

            sio.emit('correct answer', {'partner': False, 'objs': objs},
                     room=sid, namespace='/game')
            sio.emit('correct answer', {'partner': True},
                     room=clients_partner[sid], namespace='/game')
        else:
            sio.emit('incorrect answer', {'obj': obj, 'partner': False},
                     room=sid, namespace='/game')
            sio.emit('incorrect answer', {'obj': obj, 'partner': True},
                     room=clients_partner[sid], namespace='/game')
            logout([sid, clients_partner[sid]])

@sio.on('guess annotation', namespace='/game')
def guess(sid, ann_id):
    if questioner_anns[sid][questioner_annid[sid]]['id'] == ann_id:
        sio.emit('correct annotation', {'partner': False},
                 room=sid, namespace='/game')
        sio.emit('correct annotation', {'partner': True},
                 room=clients_partner[sid], namespace='/game')
    else:
        sio.emit('wrong annotation', {'partner': False},
                 room=sid, namespace='/game')
        sio.emit('wrong annotation', {'partner': True},
                 room=clients_partner[sid], namespace='/game')
    logout([sid, clients_partner[sid]])

@sio.on('next', namespace='/game')
def next(sid):
    partnerid = False
    for id, user in clients_waiting.items():
        if id != sid and user:
            partnerid = id

    if partnerid:
        clients_partner[partnerid] = sid
        clients_partner[sid] = partnerid
        role = (random.random() > 0.5)
        ind = random.randint(0, 1500)
        obj = db.find_one({'i': ind})
        ann_ind = random.randint(0, len(obj['annotations']) - 1)
        ann = obj['annotations'][ann_ind]

        if role:
            questioner_anns[id] = obj['annotations']
            questioner_annid[id] = ann_ind
            sio.emit('questioner',
                     {'img': ('https://msvocds.blob.core.windows.net/'
                              'imgs/{}.jpg').format(obj['id'])},
                     room=id,
                     namespace='/game')
            sio.emit('answerer',
                     {'img': ('https://msvocds.blob.core.windows.net/'
                              'imgs/{}.jpg').format(obj['id']),
                      'poly_x': ann['poly_x'],
                      'poly_y': ann['poly_y'],
                      'name': ann['category'],
                      'catid': ann['catid']},
                     room=sid,
                     namespace='/game')
        else:
            questioner_anns[sid] = obj['annotations']
            questioner_annid[sid] = ann_ind
            sio.emit('answerer',
                     {'img': ('https://msvocds.blob.core.windows.net/'
                              'imgs/{}.jpg').format(obj['id']),
                      'poly_x': ann['poly_x'],
                      'poly_y': ann['poly_y'],
                      'name': ann['category'],
                      'catid': ann['catid']},
                     room=id,
                     namespace='/game')
            sio.emit('questioner',
                     {'img': ('https://msvocds.blob.core.windows.net/'
                              'imgs/{}.jpg').format(obj['id'])},
                     room=sid,
                     namespace='/game')

        del clients_waiting[partnerid]
    else:
        clients_waiting[sid] = True
        sio.emit('no partner',
                 {},
                 room=sid,
                 namespace='/game')


@sio.on('connect', namespace='/game')
def connect(sid, re):
    print 'connect' + sid


@sio.on('disconnect', namespace='/game')
def disconnect(sid):
    if sid in clients_waiting:
        del clients_waiting[sid]
    if sid in clients_partner:
        partnerid = clients_partner[sid]
        sio.emit('partner_disconnect',
                 '',
                 room=clients_partner[sid],
                 namespace='/game')

        clients_waiting[partnerid] = True
        logout([sid, partnerid])


def logout(sids):
    for sid in sids:
        if sid in clients_partner:
            del clients_partner[sid]
        if sid in questioner_anns:
            del questioner_anns[sid]
        if sid in questioner_annid:
            del questioner_annid[sid]
