# tm1cmp
This is a simple utility to compare 2 tm1 views and see whether the values are different.

You can:
- export a view to a csv file and compare against the previously exported file later on
- compare a view on 2 different TM1 servers

Views can be defined:
- native, i.e. named views in TM1
- MDX statements
- based on some selections and randomisation, i.e. select 2020 results for 100 random Cost Centres

### Use cases:
- changing rules or feeders in a model and testing that changes haven't broken anything. Instead of snapshotting values to Excel manually and building reconciliation workbooks, you can define the comparison points and run them more frequently
- TM1 version upgrades: you can compare old vs new models to ensure you still got the same values in cubes
- CI / CD pipelines

### How it works:
- we define the comparisons in json file of a format like this (see checks folder for a set of examples)
'''
{
  "$schema": "./schema.json",
  "name": "export to a text file",
  "tolerance":0.00001,
  "source": {
    "type": "tm1",
    "server": "planning_sample_prod",
    "cube":"plan_BudgetPlan",
    "view_name": "Goal Input",
    "view_type": "native"
  },
  "target": {
    "type": "file",
    "folder": "data_export"
  }
}
'''
- running 'tm1cmp.exe -i check_file.json' will export data from selected view to a file and generate a reverse definition check of this file agains the view
- any variances in comparison will generate a 'source ' vs 'target' comparison file
- connection config file should contain the required information to connect to your TM1 instance


### Additional information:
- You can run multiple comparisons at the same time by running 'tm1cmp.exe -i folder_with_json_files', this will run 5 threads of comparisons in parallel. Number of threads to run in parallel can be adjusted with -t parameter, so 'tm1cmp.exe -i folder_with_json_files -t 10' will run 10 threads
- tolerance parameter in the check definition allows you to define what level of variance is 'acceptable'. Sometimes you'd get differences 5th or 6th decimal point due to spreading or allocation variances between tm1 servers.