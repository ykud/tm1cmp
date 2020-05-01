# tm1cmp
TM1CMP is a utility to run a 'check' to compare 2 tm1 views and show the variance. TM1CMP is built on [TM1Py](https://github.com/cubewise-code/tm1py) project, making TM1-related part of it a breeze.

You can:
- export a view to a csv file and compare against the previously exported file
- compare a view on 2 different TM1 servers

Views can be:
- named views in TM1 -- native views 
- defined by MDX statements including some randomisation, i.e. select 2020 results for 100 random Cost Centres

# Use cases:
- changing rules or feeders in a model and testing that changes haven't broken anything. Instead of snapshotting values to Excel manually and building reconciliation workbooks, you can define the comparison points and run them more frequently as you go along
- validating the impact of code changes / deployment -- snapshot the most important model cubes before deployment, deploy your changes and run checks to analyse the impact
- TM1 version upgrades: you can compare old vs new servers to ensure you still got the same data
- CI / CD pipelines

# How it works:
- define the comparisons in json file of a format like this ([see more examples](checks/))
```
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
```
- running `tm1cmp.exe -i check_file.json` will export data from selected view to a file and generate a reverse definition check of this file agains the view
- any variances in comparison will generate a 'source ' vs 'target' comparison csv file like this:

| change_type |cell | source_value | target_value |
| --- | --- | --- | --- |
| change |('[plan_version].[plan_version].[FY 2004 Budget]', ..., '[plan_time].[plan_time].[Q2-2004]') | 438828258.9301186 | 438828258.9301184 |
| add | ('[plan_version].[plan_version].[FY 2004 Budget]', ... ,'[plan_time].[plan_time].[2004]') | 0 | 4135447577.641119 |

- connection [config file](config.ini) should contain the required information to connect to your TM1 instance, all TM1 authentication modes are supported

# How to run:
- download the tm1cmp.exe from [Releases](https://github.com/ykud/tm1cmp/releases) tab of this project (windows only). Run from source with python in Linux or MacOS.
- create config file defining how to connect to your PA server (s) -- [see example](config.ini)
- create comparison json file -- [see examples](checks/)
- run `tm1cmp.exe -i check_file.json` from command line

# Additional information:
- You can run multiple comparisons at the same time by running `tm1cmp.exe -i folder_with_json_files`, this will run 5 threads of comparisons in parallel. Number of threads to run in parallel can be adjusted with -t parameter, so `tm1cmp.exe -i folder_with_json_files -t 10` will run 10 threads
- tolerance parameter in the check definition allows you to define what level of variance is 'acceptable'. Sometimes you'd get differences 5th or 6th decimal point due to spreading or allocation variances between tm1 servers
- tm1cmp.exe returns 0 code if checks are sucessfull and 1 if there's variance or errors in checks

# How to build exe from source
- required libraries:
- - keyring
- - TM1Py
- [pyinstaller command to build exe](pyinstaller_build_win.bat)

# Ideas and enhancements
Any feedback and ideas are very welcome, please raise issues in this repository.
