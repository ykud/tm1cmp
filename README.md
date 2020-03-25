# tm1diff
This is a simple utility to compare 2 tm1 models and see whether the values are different.

Use case:
* changing rules or feeders in a model and testing that new model behaves the same as the old one

What it does:
* we define the test points (via a json or csv file), i.e. the views that should return the same values in both models (or the same models and different cubes / views)
* we should be able to randomise the test point views as well (i.e. create random 100 views based on cost centres) as part of our parametrisation

How it works:
* read the test points file
* run py.test for each test point? 
* connect to source & target models and create views as described and compare them
* connection config file will contain the required information to connect to both instances

Test point file format:
* I want it to be human-editable and very friendly
* maybe a file per test and an ability to run tool with wildcards in file names to run multiple tests?
* should support:
    ** named views 
    ** creating a view dynamically with selecting a set of elements, dimension subset or randomizer?
    ** MDX views?


How do we want to see differences in cellset output?