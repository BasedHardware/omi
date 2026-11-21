package main

import (
	"errors"
	"regexp"
	"strconv"
)

type eraseConfig struct {
	port           int
	audience       string
	subject        string
	cert           string
	key            string
	markerProject  string
	markerDatabase string
}

var (
	serviceSubject   = regexp.MustCompile(`^[0-9]{1,32}$`)
	markerDatabaseID = regexp.MustCompile(`^(\(default\)|[a-z][a-z0-9-]{2,61}[a-z0-9])$`)
)

func (c *config) readEraseConfig(lookup lookupEnv) error {
	rawPort, enabled := lookup("ERASE_PORT")
	if !enabled {
		return nil
	}
	port, err := strconv.Atoi(rawPort)
	if err != nil || port < 1 || port > 65535 || port == c.healthPort || port == c.metricsPort {
		return errors.New("ERASE_PORT must be a distinct port between 1 and 65535")
	}
	audience, _ := lookup("ERASE_AUDIENCE")
	subject, _ := lookup("ERASE_CALLER_SUBJECT")
	cert, _ := lookup("ERASE_TLS_CERT")
	key, _ := lookup("ERASE_TLS_KEY")
	if audience == "" || !serviceSubject.MatchString(subject) || cert == "" || key == "" {
		return errors.New("queue erase listener requires audience, workload subject and TLS files")
	}
	project, _ := lookup("ERASE_FIRESTORE_PROJECT")
	database, _ := lookup("ERASE_FIRESTORE_DATABASE")
	if !projectID.MatchString(project) || !markerDatabaseID.MatchString(database) {
		return errors.New("queue erase listener requires ERASE_FIRESTORE_PROJECT and ERASE_FIRESTORE_DATABASE")
	}
	c.erase = eraseConfig{
		port: port, audience: audience, subject: subject, cert: cert, key: key,
		markerProject: project, markerDatabase: database,
	}
	return nil
}
