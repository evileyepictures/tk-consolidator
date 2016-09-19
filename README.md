# SG Toolkit Consolidator App

### NAME
consolidator - command line application that prepare production assets for delivery

### SYNOPSIS

```
tank consolidator -id DELIVERY_ID
```

### DESCRIPTION
Consolidator works with Shotgun Delivery entities. Each of this entity represent a single delivery. For each delivery on SG the publish type has to be specified. This types determined by production typically for every external vendor.
Multiple Version as well as PublishedFiles can be attached to a particular delivery. Consolidator will look at this attachments and find all corresponding movies and file sequences. Those attachments will be copy to new location according to path template for the given delivery type.

Running consolidator command with no argument will print the following help:
```
usage: toolkit.py [-h] -id ID [-stf TYPE [TYPE ...]] [-ef EXT [EXT ...]]

command line application that prepare production assets for delivery

optional arguments:
  -h, --help            show this help message and exit
  -id ID                shotgun delivery id
  -stf TYPE [TYPE ...]  exclude assets from processing by its shotgun entity
                        type
  -ef EXT [EXT ...]     exclude assets from processing by its extension
```

### EXAMPLES

Publishing delivery for Bolden project with ID 37:
```
sgbld consolidator -id 37
```
