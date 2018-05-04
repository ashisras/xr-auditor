# Auditor

## Introduction

This application enables **periodic auditing** of the linux shells in the IOS-XR container-based architecture by running **individual python applications in each individual environment in IOS-XR   
(across Active-Standby HA systems)**, i.e.:  

>*   XR-LXC     
>*   ADMIN-LXC   
>*   HOST    
  

**Functionally**, the individual python applications:  

>*  **Collect local data based on a YAML based user-config** provided during the build process 
>*  **Store accummulated data in the form of XML that is strictly validated against a user-defined XML schema**.
>*  **Send the accummulated XML data periodically to an external server over SSH** where it may be easily processed and visualized using any tools that can consume the XML schema and the data.

Further, the **application supports**:  

>1.  **Installation**: on a High-Availability (Active/Standby RP) system through a single command.  
>2.  **A clean uninstallation**  across the entire system through a single command.  
>3.  **Troubleshooting**:   **Dump filesystem view** - The ability to view the entire system's affected (user-defined in YAML file) system across active/standby RPs using a single command.  
>4.  **Troubleshooting**:   **Gather debug Data** - The ability to collect generated logs from all the environments (Active/Standby XR LXC, Admin LXC, HOST) and create a single tar ball using a single command.  
    
    
No SMUs needed, leverages the native app-hosting architecture in IOS-XR and the internal SSH-based access between different parts of the IOS-XR architecture - namely, XR-LXC, Admin-LXC and HOST of the active and/or Standby RPs to easily manage movement of data, logs and apps across the system.




## User Story

<a href="/user_story_auditor.png">![user-story](/user_story_auditor.png)</a>






    
