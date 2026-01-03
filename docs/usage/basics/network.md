# Network Configuration

```{note}
**You are responsible to ensure that you are connected to Argonne's network securely.**
```

Argo, more percisely, the Argo gateway API, is

1. an internal service behind Argonne's firewall.
2. at the moment, only accessible from certain ANL hosts.

These two conditions combined mean that there might be some network configuration required to use the Argo service. Here are some common scenarios:

## Scenario 1: On Argonne Campus

You are (physically, or virtually) on Argonne's campus. First thing to do is to figure out if your machine/host can reach the Argo gateway API. You can do this by one of the following:

- `curl --max-time 5 https://apps.inside.anl.gov/argoapi/api/v1/resource/embed/` to see if it returns a JSON response.
- open a browser and navigate to `https://apps.inside.anl.gov/argoapi/api/v1/resource/embed/` to see if it returns something.

### If you can reach the Argo gateway API

A successful response may look like this:

```json
{ "detail": "Method Not Allowed" }
```

Then you are good to set up the Argo proxy by following the [installation guide](../installation.md).

### If you cannot reach the Argo gateway API

It's possible that your machine/host is not configured to access Argo API service. Now you have two options:

1. Submit a [vector ticket](https://servicenow.anl.gov/sp?id=sc_cat_item&sys_id=c9c09caadbb408d04c6562eb8a96194d) to set up a firewall conduit for your machine/host. Instructions for the ticket:

   ```plaintext
   Description: "Need access to the Argo Gateway API endpoints."
   Object Group Information: Select "BIS_Argo_Access" from the drop-down menu
   Object-Group Additions: Click [Add] button
   Pop-up window: IP Address or Network: Enter IP address.
   Repeat the process to add more than one IP address.
   ```

2. Deploy the Argo proxy on another machine that can reach the Argo gateway API. Access the proxy via its IP address or hostname. For example, deploying on port 44497 of an ANL machine would give URLs like `http://some_machine.cels.anl.gov:44497` or `http://some_machine:44497`.

## Scenario 2: Off Argonne Campus

If you are off Argonne campus, you can use either of the following methods to access the Argo gateway API:

1. VPN: Connect to Argonne VPN and then follow the steps in [Scenario 1](#scenario-1-on-argonne-campus).
2. SSH tunnel: Set up an SSH tunnel to a machine on Argonne campus that can reach the Argo gateway. Make sure that machine you tunnel to is able to reach the Argo gateway API, by following the steps in [Scenario 1](#scenario-1-on-argonne-campus).

Candidate machines might be the Windows/Linux PC, Mac in your office, or some server you have access to.

Good luck!
