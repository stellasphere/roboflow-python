import requests
import json
from roboflow.core.project import Project
from roboflow.config import *
import sys
import glob

from roboflow.util.active_learning_utils import count_class_occurances, count_comparisons, check_box_size, base64_encode, clip_encode

class Workspace():
    def __init__(self, info, api_key, default_workspace, model_format):
        if api_key == "coco-128-sample":
            self.__api_key = api_key
            self.model_format = model_format
        else:
            workspace_info = info['workspace']
            self.name = workspace_info['name']
            self.project_list = workspace_info['projects']
            if "members" in workspace_info.keys():
                self.members = workspace_info['members']
            self.url = workspace_info['url']
            self.model_format = model_format

            self.__api_key = api_key

    def list_projects(self):
        """Lists projects out in the workspace
        """
        print(self.project_list)

    def projects(self):
        """Returns all projects as Project() objects in the workspace
        :return an array of project objects
        """
        projects_array = []
        for a_project in self.project_list:
            proj = Project(self.__api_key, a_project, self.model_format)
            projects_array.append(proj.name)

        return projects_array

    def project(self, project_name):
        sys.stdout.write("\r" + "loading Roboflow project...")
        sys.stdout.write("\n")
        sys.stdout.flush()

        if self.__api_key == "coco-128-sample":
            return Project(self.__api_key, {}, self.model_format)
        
        project_name = project_name.replace(self.url + "/", "")

        if "/" in project_name:
            raise RuntimeError("The {} project is not available in this ({}) workspace".format(project_name, self.url))

        dataset_info = requests.get(API_URL + "/" + self.url + "/" + project_name + "?api_key=" + self.__api_key)

        # Throw error if dataset isn't valid/user doesn't have permissions to access the dataset
        if dataset_info.status_code != 200:
            raise RuntimeError(dataset_info.text)

        dataset_info = dataset_info.json()['project']

        return Project(self.__api_key, dataset_info, self.model_format)

    def active_learning(self, raw_data, inference_endpoint, upload_destination, conditionals):
        '''
        @params:
            raw_data: dir = folder of images, or videos, to be processed
            inference_endpoint: List[str, int] = name of the project
            upload_destination: str = name of the upload project
            conditionals: dict = dictionary of upload conditions
        '''

        inference_model = self.project(inference_endpoint[0]).version(inference_endpoint[1]).model
        upload_project = self.project(upload_destination)

        print("inference reference point: ", inference_model)
        print("upload destination: ", upload_project)

        # TODO: work with raw_data
        # TODO: extention and globbing properties added to config
        video_extention = ".png"
        globbed_files = glob.glob(raw_data + '/*' + video_extention)

        for index, image in enumerate(globbed_files):
            print("*** Processing image [" + str(index + 1) + "/" + str(len(globbed_files)) + "] - " + image + " ***")

            # perform inference on image
            # TODO: mention 403 error
            predictions = inference_model.predict(image).json()['predictions']
            
            # compare object and class count of predictions if enabled, continue if not enough occurances
            if(not count_comparisons(predictions, conditionals["required_objects_count"], conditionals["required_class_variance_count"], conditionals["target_classes"])):
                print(' [X] image failed count cases')
                continue 

            # iterate through all predictions
            for prediction in predictions:

                # check if box size of detection fits requirements
                if not check_box_size(prediction, conditionals["minimum_size_requirement"], conditionals["maximum_size_requirement"]):
                    print(' [X] prediction failed box size cases')
                    continue

                # compare confidence of detected object to confidence thresholds
                # confidence comes in as a .XXX instead of XXX%
                if(prediction['confidence'] * 100 >= conditionals["confidence_interval"][0] and 
                    prediction['confidence'] * 100 <= conditionals["confidence_interval"][1]):
                
                    # filter out non-target_class uploads if enabled
                    if(len(conditionals["target_classes"]) > 0 and
                        prediction['class'] not in conditionals["target_classes"]):
                        print(' [X] prediction failed target_classes')
                        continue

                    # upload on success!
                    print(' >> image uploaded!')
                    upload_project.upload(image, num_retry_uploads=3)
                    break

        return

    def __str__(self):
        projects = self.projects()
        json_value = {'name': self.name,
                      'url': self.url,
                      'projects': projects
                      }

        return json.dumps(json_value, indent=2)
