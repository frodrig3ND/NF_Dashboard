from app import create_app, db
from app.stats.models import Strava_Activity, Fitbit_Weight, Fitbit_Calories
from sqlalchemy import inspect
import json
from stats_con import Strava, Fitbit
from collections import defaultdict
import logging
import datetime
from datetime import timedelta
import prefect
from prefect import Flow, Parameter, task, unmapped
from prefect.schedules import IntervalSchedule

app = create_app('config.Test_Config')
app.app_context().push()

#Initialize logging set level to Debug
log= logging.getLogger()
console=logging.StreamHandler()
format_str = '%(asctime)s\t%(levelname)s -- %(processName)s %(filename)s:%(lineno)s -- %(message)s'
console.setFormatter(logging.Formatter(format_str))
log.addHandler(console)
log.setLevel(logging.DEBUG)

db.create_all(app=app)
session=db.session

@task(max_retries=2, retry_delay=timedelta(seconds=2))
def Update_Strava_Activities():
    # Initialize Strava connection and get the data
    stv=Strava()
    data=stv.get_activities().json()

    # Get the required columns from our Strava Class
    strava_params=[c for c in inspect(Strava_Activity).columns.keys()]

    # Remove the last time parameter as that is autogenerated
    strava_params.remove('last_time')

    #We will first create all our model class instances for Strava_Activity
    acts=[]
    for dic in data:
        #Initialize an empty default dict so we dont get triped up with key missing issues
        d = defaultdict(lambda: None, dic)
        #Rename some columns from the API json so they match our class
        d['owner']=d['athlete']['id']
        d['activity_type']=d['type']

        #Search for values needed in our class in the API json
        update={}
        for val in strava_params:
            update[val]=d[val]

        log.info(update)

        #Initialize our model class from the dictionary
        act=Strava_Activity(**update)
        acts.append(act)

    # Merge our results into the database (I will rewrite all of them for the last 30 items regardless of what it says), at the current moment I don't need to check the API for deleted activities but might in the future.
    for act in acts:
        try:
            with session.begin_nested():
                session.merge(act)
            log.info("Updated: %s"%str(act))
        except:
            log.info("Skipped %s"%str(act))
    session.commit()
    session.flush()

# Repeate the same process for the Fitbit_Weight Class
@task(max_retries=2, retry_delay=timedelta(seconds=2))
def Update_Fitbit_Weight():
    fbt=Fitbit()
    wdata=fbt.get_weight().json()

    fweight_params=[c for c in inspect(Fitbit_Weight).columns.keys()]
    fweight_params.remove('last_time')

    acts=[]

    for dic in wdata['weight']:
        d = defaultdict(lambda: None, dic)
        d['id']=d['logId']
        d['record_date']=d['date']
        d['record_time']=d['time']

        update={}
        for val in fweight_params:
            update[val]=d[val]

        act=Fitbit_Weight(**update)
        acts.append(act)

    for act in acts:
        try:
            with session.begin_nested():
                session.merge(act)
            log.info("Updated: %s"%str(act))
        except:
            log.info("Skipped %s"%str(act))
    session.commit()
    session.flush()

@task(max_retries=2, retry_delay=timedelta(seconds=2))
def Update_Fitbit_Calories():
    fbt=Fitbit()
    #The calories dont have an ID so create one out of the date
    cdata=fbt.get_calories().json()
    acts=[]
    for dic in cdata['foods-log-caloriesIn']:
        d = defaultdict(lambda: None, dic)
        update={}
        update['id']=int(datetime.datetime.strptime(d['dateTime'], '%Y-%m-%d').timestamp())
        update['record_date']=d['dateTime']
        update['calories']=d['value']

        act=Fitbit_Calories(**update)
        acts.append(act)

    for act in acts:
        try:
            with session.begin_nested():
                session.merge(act)
            log.info("Updated: %s"%str(act))
        except:
            log.info("Skipped %s"%str(act))
    session.commit()
    session.flush()


schedule = IntervalSchedule(interval=timedelta(minutes=1))

with Flow("Data Updater", schedule) as flow:
    Update_Strava_Activities()
    Update_Fitbit_Weight()
    Update_Fitbit_Calories()

#flow.visualize()
flow.run()
