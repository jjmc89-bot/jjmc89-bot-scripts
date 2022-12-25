CREATE TABLE IF NOT EXISTS users (
    user_id                     INT(10) UNSIGNED PRIMARY KEY,
    user_name                   VARCHAR(255) NOT NULL,
    user_last_rev_id            INT(10) UNSIGNED,
    user_last_rev_timestamp     CHAR(14),
    user_last_log_id            INT(10) UNSIGNED,
    user_last_log_timestamp     CHAR(14),
    user_c2_editcount           INT(11)      NOT NULL,
    user_c2_desysop_timestamp   CHAR(14),
    user_c2_risk_editcount      INT(11)      NOT NULL,
    user_sysop                  TINYINT(1)   NOT NULL,
    user_bot                    TINYINT(1)   NOT NULL DEFAULT 0,
    user_bureaucrat             TINYINT(1)   NOT NULL DEFAULT 0,
    user_last_updated_timestamp CHAR(14)     NOT NULL
) ENGINE = InnoDB, DEFAULT CHARACTER SET = utf8mb4;

CREATE TABLE IF NOT EXISTS notifications (
    note_id            INT(10) UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    note_user_id       INT(10) UNSIGNED    NOT NULL,
                       CONSTRAINT fk_user_id
                       FOREIGN KEY (note_user_id) REFERENCES users (user_id)
                       ON DELETE CASCADE
                       ON UPDATE CASCADE,
    note_type          TINYINT(1) UNSIGNED NOT NULL,
    note_rev_id        INT(10) UNSIGNED    NOT NULL UNIQUE KEY,
    note_rev_timestamp CHAR(14)            NOT NULL
) ENGINE = InnoDB, DEFAULT CHARACTER SET = utf8mb4;
