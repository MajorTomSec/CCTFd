import hashlib
import json
import os
import datetime

from flask import current_app as app, render_template, request, redirect, jsonify, url_for, Blueprint, \
    abort, render_template_string, send_file, session
from passlib.hash import bcrypt_sha256
from sqlalchemy.sql import not_, or_
from sqlalchemy.exc import IntegrityError

from CTFd.plugins import register_plugin_assets_directory
from CTFd.plugins.challenges import *
from CTFd.plugins.keys import get_key_class
from CTFd.models import db, Challenges, Files, Solves, WrongKeys, Keys, Tags, Teams, Awards, Hints, Unlocks
from CTFd.plugins.keys import get_key_class
from flask import render_template

from CTFd.models import db
from CTFd.utils import admins_only, is_admin

from CTFd import utils
from CTFd.utils import override_template
import os
from CTFd.utils import text_type

cctfd = Blueprint('cctfd', __name__)

class CommunityChallenge(BaseChallenge):
    id = "community"  # Unique identifier used to register challenges
    name = "community"  # Name of a challenge type
    templates = {  # Nunjucks templates used for each aspect of challenge editing & viewing
        'create': '/plugins/CCTFd/assets/community-challenge-create.njk',
        'update': '/plugins/CCTFd/assets/community-challenge-update.njk',
        'modal': '/plugins/CCTFd/assets/community-challenge-modal.njk',
    }
    scripts = {  # Scripts that are loaded when a template is loaded
        'create': '/plugins/CCTFd/assets/community-challenge-create.js',
        'update': '/plugins/CCTFd/assets/community-challenge-update.js',
        'modal': '/plugins/CCTFd/assets/community-challenge-modal.js',
    }

    @staticmethod
    def create(request):
        """
        This method is used to process the challenge creation request.
        :param request:
        :return:
        """
        # Create challenge
        chal = CommunityChallengeModel(
            name=request.form['name'],
            description=request.form['description'],
            value=request.form['value'],
            category=request.form['category'],
            type=request.form['chaltype'],
            owner=session['id']
        )

        # Never hide Community challenges
        chal.hidden = False

        max_attempts = request.form.get('max_attempts')
        if max_attempts and max_attempts.isdigit():
            chal.max_attempts = int(max_attempts)

        db.session.add(chal)
        db.session.commit()

        flag = Keys(chal.id, request.form['key'], request.form['key_type[0]'])
        if request.form.get('keydata'):
            flag.data = request.form.get('keydata')
        db.session.add(flag)

        db.session.commit()

        files = request.files.getlist('files[]')
        for f in files:
            utils.upload_file(file=f, chalid=chal.id)

        db.session.commit()

    @staticmethod
    def read(challenge):
        """
        This method is in used to access the data of a challenge in a format processable by the front end.
        :param challenge:
        :return: Challenge object, data dictionary to be returned to the user
        """
        challenge = CommunityChallengeModel.query.filter_by(id=challenge.id).first()

        own = (challenge.owner == session['id'])
        owner = Teams.query.filter(Teams.id == challenge.owner).first().name


        data = {
            'id': challenge.id,
            'name': challenge.name,
            'value': challenge.value,
            'description': challenge.description,
            'category': challenge.category,
            'hidden': challenge.hidden,
            'max_attempts': challenge.max_attempts,
            'owner': owner,
            'own': own,
            'type': challenge.type,
            'type_data': {
                'id': CommunityChallenge.id,
                'name': CommunityChallenge.name,
                'templates': CommunityChallenge.templates,
                'scripts': CommunityChallenge.scripts,
            },
        }

        if own == True:
            data.update({
                'nonce': session.get('nonce')
            })

        return challenge, data

    @staticmethod
    def update(challenge, request):
        """
        This method is used to update the information associated with a challenge. This should be kept strictly to the
        Challenges table and any child tables.
        :param challenge:
        :param request:
        :return:
        """
        challenge = CommunityChallengeModel.query.filter_by(id=challenge.id).first()

        challenge.name = request.form['name']
        challenge.description = request.form['description']
        challenge.value = int(request.form.get('value', 0)) if request.form.get('value', 0) else 0
        challenge.max_attempts = int(request.form.get('max_attempts', 0)) if request.form.get('max_attempts', 0) else 0
        challenge.category = request.form['category']

        # Never hide Community challenges
        challenge.hidden = False

        db.session.commit()
        db.session.close()

    @staticmethod
    def delete(challenge):
        """
        This method is used to delete the resources used by a challenge.
        :param challenge:
        :return:
        """

        # delete bonus award
        # TODO: kinda hack-ish (mod Awards table instead ?)
        owner = CommunityChallengeModel.query.filter(CommunityChallengeModel.id == challenge.id).first().owner
        name = "Bonus points for submitting challenge " + challenge.name
        Awards.query.filter_by(teamid=owner, name=name, value=challenge.value).delete()

        # delete all other resources
        WrongKeys.query.filter_by(chalid=challenge.id).delete()
        Solves.query.filter_by(chalid=challenge.id).delete()
        Keys.query.filter_by(chal=challenge.id).delete()
        files = Files.query.filter_by(chal=challenge.id).all()
        for f in files:
            utils.delete_file(f.id)
        Files.query.filter_by(chal=challenge.id).delete()
        Tags.query.filter_by(chal=challenge.id).delete()
        Hints.query.filter_by(chal=challenge.id).delete()
        CommunityChallengeModel.query.filter_by(id=challenge.id).delete()
        Challenges.query.filter_by(id=challenge.id).delete()
        db.session.commit()

    @staticmethod
    def attempt(chal, request):
        """
        This method is used to check whether a given input is right or wrong. It does not make any changes and should
        return a boolean for correctness and a string to be shown to the user. It is also in charge of parsing the
        user's input from the request itself.
        :param chal: The Challenge object from the database
        :param request: The request the user submitted
        :return: (boolean, string)
        """
        if chal.owner == session['id']:
            return False, "Not allowed"

        provided_key = request.form['key'].strip()
        chal_keys = Keys.query.filter_by(chal=chal.id).all()
        for chal_key in chal_keys:
            if get_key_class(chal_key.type).compare(chal_key.flag, provided_key):
                return True, 'Correct'
        return False, 'Incorrect'

    @staticmethod
    def solve(team, chal, request):
        """
        This method is used to insert Solves into the database in order to mark a challenge as solved.
        :param team: The Team object from the database
        :param chal: The Challenge object from the database
        :param request: The request the user submitted
        :return:
        """
        chal = CommunityChallengeModel.query.filter_by(id=chal.id).first()
        solve_count = Solves.query.join(Teams, Solves.teamid == Teams.id).filter(Solves.chalid == chal.id, Teams.banned == False).count()

        # if this is the first validation, we give the bonus points to the chal's owner
        if solve_count == 0:
            award = Awards(teamid=chal.owner, name=text_type('Bonus points for submitting challenge {}'.format(chal.name)), value=chal.value)
            db.session.add(award)

        provided_key = request.form['key'].strip()
        solve = Solves(teamid=team.id, chalid=chal.id, ip=utils.get_ip(req=request), flag=provided_key)
        db.session.add(solve)
        db.session.commit()
        db.session.close()

    @staticmethod
    def fail(team, chal, request):
        """
        This method is used to insert WrongKeys into the database in order to mark an answer incorrect.
        :param team: The Team object from the database
        :param chal: The Challenge object from the database
        :param request: The request the user submitted
        :return:
        """
        provided_key = request.form['key'].strip()
        wrong = WrongKeys(teamid=team.id, chalid=chal.id, ip=utils.get_ip(request), flag=provided_key)
        db.session.add(wrong)
        db.session.commit()
        db.session.close()

class CommunityChallengeModel(Challenges):
    __mapper_args__ = {'polymorphic_identity': 'community'}
    id = db.Column(None, db.ForeignKey('challenges.id'), primary_key=True)
    owner = db.Column(db.Integer, db.ForeignKey('teams.id'))

    def __init__(self, name, description, value, category, type='community', owner=1):
        self.name = name
        self.description = description
        self.value = value
        self.initial = value
        self.category = category
        self.type = type
        self.owner = owner

def load(app):
    app.db.create_all()
    register_plugin_assets_directory(app, base_path='/plugins/CCTFd/assets/')

    # create new challenge type
    CHALLENGE_CLASSES['community'] = CommunityChallenge

    # Replace templates
    dir_path = os.path.dirname(os.path.realpath(__file__))

    base_path = os.path.join(dir_path, 'community-base.html')
    create_path = os.path.join(dir_path, 'create.html')
    chal_path = os.path.join(dir_path, 'challenges.html')

    override_template('base.html', open(base_path).read())
    override_template('admin/chals/create.html', open(create_path).read())
    override_template('challenges.html', open(chal_path).read())

    # replace /chals route
    def chals():
        if not utils.is_admin():
            if not utils.ctftime():
                if utils.view_after_ctf():
                    pass
                else:
                    abort(403)

        if utils.get_config('verify_emails'):
            if utils.authed():
                if utils.is_admin() is False and utils.is_verified() is False:  # User is not confirmed
                    abort(403)

        if utils.user_can_view_challenges() and (utils.ctf_started() or utils.is_admin()):
            teamid = session.get('id')
            chals = Challenges.query.filter(or_(Challenges.hidden != True, Challenges.hidden == None)).order_by(Challenges.value).all()

            json = {'game': []}
            for x in chals:
                tags = [tag.tag for tag in Tags.query.add_columns('tag').filter_by(chal=x.id).all()]
                files = [str(f.location) for f in Files.query.filter_by(chal=x.id).all()]
                unlocked_hints = set([u.itemid for u in Unlocks.query.filter_by(model='hints', teamid=teamid)])
                hints = []
                for hint in Hints.query.filter_by(chal=x.id).all():
                    if hint.id in unlocked_hints or utils.ctf_ended():
                        hints.append({'id': hint.id, 'cost': hint.cost, 'hint': hint.hint})
                    else:
                        hints.append({'id': hint.id, 'cost': hint.cost})
                chal_type = get_chal_class(x.type)

                if chal_type == CommunityChallenge:
                    owner_id = CommunityChallengeModel.query.filter(CommunityChallengeModel.id == x.id).first().owner
                else:
                    owner_id = 1

                owner = Teams.query.filter(Teams.id == owner_id).first().name
                own = (owner_id == session['id'])

                chal_data = {
                    'id': x.id,
                    'type': chal_type.name,
                    'name': x.name,
                    'value': x.value,
                    'description': x.description,
                    'category': x.category,
                    'files': files,
                    'tags': tags,
                    'hints': hints,
                    'owner': owner,
                    'own': own,
                    'template': chal_type.templates['modal'],
                    'script': chal_type.scripts['modal']
                }

                if own == True:
                    chal_data.update({
                        'nonce': session.get('nonce')
                    })

                json['game'].append(chal_data)

            db.session.close()
            return jsonify(json)
        else:
            db.session.close()
            abort(403)
    app.view_functions['challenges.chals'] = chals

    # create /community/chal_types route
    @app.route('/community/chal_types', methods=['GET'])
    def user_chal_types():
        data = {}
        for class_id in CHALLENGE_CLASSES:
            challenge_class = CHALLENGE_CLASSES.get(class_id)

            # only allow CommunityChallenge for non-admin users
            if not utils.is_admin() and challenge_class != CommunityChallenge:
                continue

            data[challenge_class.id] = {
                'id': challenge_class.id,
                'name': challenge_class.name,
                'templates': challenge_class.templates,
                'scripts': challenge_class.scripts,
            }

        return jsonify(data)

    # create /community/new route
    @app.route('/community/new', methods=['GET', 'POST'])
    def user_create_chal():
        if request.method == 'POST':
            chal_type = request.form['chaltype']
            chal_class = get_chal_class(chal_type)

            # do not allow non-admin users to create non-community challenges
            if not utils.is_admin() and chal_class != CommunityChallenge:
                abort(403)

            chal_class.create(request)
            return redirect(url_for('challenges.challenges_view'))
        else:
            return render_template('admin/chals/create.html', content=open(create_path).read())

    # create /community/update route
    @app.route('/community/update', methods=['POST'])
    def user_update_chal():
        challenge = Challenges.query.filter_by(id=request.form['id']).first_or_404()
        chal_class = get_chal_class(challenge.type)

        # only allow updating Community challenges
        if chal_class != CommunityChallenge:
            abort(403)

        # only allow updating the challenge if the user is the owner
        owner = CommunityChallengeModel.query.filter(CommunityChallengeModel.id == challenge.id).first().owner
        if owner != session['id']:
            abort(403)

        chal_class.update(challenge, request)
        return redirect(url_for('challenges.challenges_view'))
